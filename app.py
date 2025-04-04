from flask import Flask, request, redirect, url_for, render_template, flash, session, jsonify
import mysql.connector
from flask_bcrypt import Bcrypt
from flask_login import LoginManager, login_user, logout_user, login_required, current_user, UserMixin
import random
from datetime import datetime, timedelta
from flask_mail import Mail, Message
import numpy as np
from faiss_gpt import QnA_with_RAG_and_save

app = Flask(__name__)
app.secret_key = 'sunha'
bcrypt = Bcrypt(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Flask-Mail 설정
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 'sunha9240@gmail.com'  # 이메일 계정
app.config['MAIL_PASSWORD'] = ''  # 이메일 비밀번호

mail = Mail(app)  # Mail 객체 초기화

# MySQL 연결 설정
db_config = {
    'user': 'sunha',
    'password': '1234',
    'host': 'localhost',
    'database': 'backend'
}

def get_db_connection():
    return mysql.connector.connect(**db_config)

class User(UserMixin):
    def __init__(self, id, username, password):
        self.id = id
        self.username = username
        self.password = password

@login_manager.user_loader
def load_user(user_id):
    db = get_db_connection()
    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT * FROM Users WHERE id = %s", (user_id,))
    user = cursor.fetchone()
    cursor.close()
    db.close()
    if user:
        return User(id=user['id'], username=user['username'], password=user['password'])
    return None

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        email = request.form['email']
        hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')

        try:
            db = get_db_connection()
            cursor = db.cursor()

            # 삽입 작업
            cursor.execute("INSERT INTO Users (username, password, email) VALUES (%s, %s, %s)", (username, hashed_password, email))
            db.commit()  # 커밋을 빠르게 수행
        except mysql.connector.Error as e:
            db.rollback()  # 오류 발생 시 트랜잭션 롤백
            print(f"DB 오류: {e}")
        finally:
            cursor.close()
            db.close()
        flash('회원가입이 완료되었습니다.')
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        db = get_db_connection()
        cursor = db.cursor(dictionary=True)
        cursor.execute("SELECT * FROM Users WHERE username = %s", (username,))
        user = cursor.fetchone()
        cursor.close()
        db.close()
        if user and bcrypt.check_password_hash(user['password'], password):
            user_obj = User(id=user['id'], username=user['username'], password=user['password'])
            login_user(user_obj)
            return redirect(url_for('chat'))
        else:
            flash('로그인 실패. 아이디나 비밀번호를 확인하세요.')
    return render_template('login.html')


@app.route('/find_username', methods=['GET', 'POST'])
def find_username():
    if request.method == 'POST':
        email = request.form['email']
        db = get_db_connection()
        cursor = db.cursor(dictionary=True)
        cursor.execute("SELECT username FROM Users WHERE email = %s", (email,))
        user = cursor.fetchone()
        cursor.close()
        db.close()
        if user:
            return redirect(url_for('show_username', username=user['username']))
        else:
            flash("등록된 이메일이 없습니다.", 'danger')
    return render_template('find_username.html')

@app.route('/show_username/<username>')
def show_username(username):
    return render_template('show_username.html', username=username)

@app.route('/find_password', methods=['GET', 'POST'])
def find_password():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        db = get_db_connection()
        cursor = db.cursor(dictionary=True)
        cursor.execute("SELECT id FROM Users WHERE username = %s AND email = %s", (username, email))
        user = cursor.fetchone()
        cursor.close()
        db.close()

        if user:
            flash("이메일로 OTP를 전송합니다.", 'info')
            return redirect(url_for('reset_password_otp', email=email))
        else:
            flash("입력된 정보가 일치하지 않습니다.", 'danger')
    return render_template('find_password.html')



otp_codes = {}  # {email: {"otp": otp_value, "expires_at": expiration_time}}

@app.route('/reset_password_otp', methods=['GET', 'POST'])
def reset_password_otp():
    if request.method == 'POST':
        email = request.form['email']
    else:
        email = request.args.get('email')

    if email:
        db = get_db_connection()
        cursor = db.cursor(dictionary=True)
        cursor.execute("SELECT id FROM Users WHERE email = %s", (email,))
        user = cursor.fetchone()
        cursor.close()
        db.close()

        if user:
            otp = random.randint(100000, 999999)
            expiration_time = datetime.now() + timedelta(minutes=10)
            otp_codes[email] = {"otp": otp, "expires_at": expiration_time}

            # 이메일 전송
            msg = Message('비밀번호 재설정 OTP', sender='sunha9240@gmail.com', recipients=[email])
            msg.body = f'비밀번호 재설정을 위한 OTP: {otp}\n\n이 OTP는 10분 동안만 유효합니다.'
            mail.send(msg)

            flash('OTP가 이메일로 전송되었습니다.', 'info')
            return redirect(url_for('verify_otp', email=email))
        else:
            flash('입력된 이메일을 찾을 수 없습니다.', 'danger')

    return render_template('reset_password_otp.html')

@app.route('/verify_otp/<email>', methods=['GET', 'POST'])
def verify_otp(email):
    if request.method == 'POST':
        entered_otp = request.form['otp']
        otp_data = otp_codes.get(email)

        if otp_data and otp_data["otp"] == int(entered_otp) and otp_data["expires_at"] > datetime.now():
            del otp_codes[email]  # OTP 삭제
            flash('OTP 인증에 성공했습니다. 새로운 비밀번호를 설정하세요.', 'success')
            return redirect(url_for('reset_password_token', email=email))
        else:
            flash('OTP가 일치하지 않거나 만료되었습니다.', 'danger')

    return render_template('verify_otp.html')


@app.route('/reset_password_token/<email>', methods=['GET', 'POST'])
def reset_password_token(email):
    if request.method == 'POST':
        new_password = request.form['password']
        hashed_password = bcrypt.generate_password_hash(new_password).decode('utf-8')

        db = get_db_connection()
        cursor = db.cursor()
        cursor.execute("UPDATE Users SET password = %s WHERE email = %s", (hashed_password, email))
        db.commit()
        cursor.close()
        db.close()

        flash('비밀번호가 성공적으로 변경되었습니다.', 'success')
        return redirect(url_for('login'))

    return render_template('reset_password_token.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('로그아웃 되었습니다.')
    return redirect(url_for('login'))

#-----------------------------------------------------------------------------------------------------------챗봇
@app.route('/chat', methods=['GET', 'POST'])
@login_required
def chat():
    if request.method == 'GET':
        return render_template('chat.html')  # GET 요청 시 chat.html 반환
    elif request.method == 'POST':
        data = request.get_json()
        user_message = data.get('message', '')
        keyword = data.get('keyword', '')
        print(keyword)

        # 데이터베이스에 저장
        db_connection = get_db_connection()
        cursor = db_connection.cursor()

        # llm.py의 generate_response 함수 호출
        if user_message:  # 메시지가 있는 경우만 처리
            if keyword == '7. 기타':
                response_message, question, keywords, related_document = QnA_with_RAG_and_save(user_message)
            else:
                response_message, question, keywords, related_document = QnA_with_RAG_and_save(f"{keyword}에 관한 질문: {user_message}")

             
            # FAISS 또는 다른 로직에서 반환된 데이터를 변환 >>> numpy.str_ → str 변환
            related_document = str(related_document)  
            question = str(question)  
            keywords = str(keywords)  
            response_message = str(response_message)  
    
            # 4. MariaDB에 질문, 키워드, 답변 저장
            try:
                insert_query = """
                INSERT INTO QnA (question, keywords, answer, document_title)
                VALUES (%s, %s, %s, %s)
                """
                cursor.execute(insert_query, (question, keywords, response_message, related_document))
                db_connection.commit()
                cursor.close()
                db_connection.close()
            except Exception as e:
                print(f"DB 저장 중 오류 발생: {e}")

        else:
            response_message = "질문을 입력해주세요."  # 사용자 메시지가 없는 경우 기본 응답

        return jsonify({'response': response_message})  # POST 요청에 대한 JSON 응답


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True)
