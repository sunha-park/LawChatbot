import openai
import torch
import numpy as np
import faiss
from transformers import BertTokenizer, BertModel

# OpenAI API 키 설정
openai.api_key = ""
# BERT 모델과 토크나이저 로드
tokenizer = BertTokenizer.from_pretrained('bert-base-uncased')
model = BertModel.from_pretrained('bert-base-uncased')

# FAISS 인덱스 및 문서 제목 로드
index = faiss.read_index("document_faiss_index.idx")  # 미리 저장된 벡터 DB 인덱스
document_titles = np.load("document_titles.npy", allow_pickle=True)  # 문서 제목 또는 내용

# 핵심 키워드 추출 함수
def extract_keywords(question):
    prompt = f"""
    다음 사용자가 입력한 내용에서 가장 핵심인 키워드를 추출해줘.
    내용: "{question}"
    키워드:
    """
    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=50,
        temperature=0.3
    )
    return response.choices[0].message['content'].strip()


# 질의어를 사용하여 FAISS에서 가장 유사한 문서 검색
def search_similar_document(query, k=1):
    # 입력 질의어 임베딩 생성
    inputs = tokenizer(query, return_tensors='pt', truncation=True, padding=True, max_length=512)
    with torch.no_grad():
        input_embedding = model(**inputs).last_hidden_state[:, 0, :].numpy()

    input_embedding = input_embedding.astype(np.float32)  # FAISS는 float32 형식을 사용합니다

    # FAISS 인덱스를 사용하여 가장 유사한 문서 검색
    distances, indices = index.search(input_embedding, k)

    # 가장 유사한 문서 파일 제목 출력
    most_similar_index = indices[0][0]
    most_similar_title = document_titles[most_similar_index]
    
    return most_similar_title

# 질문에 대한 답변 생성 및 데이터 저장
def QnA_with_RAG_and_save(question):
    # 1. 질문에서 핵심 키워드 추출
    keywords = extract_keywords(question)

    # 2. 키워드로 관련 문서 검색
    related_document = search_similar_document(keywords)

    # 3. GPT-3.5로 답변 생성
    prompt = f"""
    넌 법률 전문가야. 문서를 참고해서 고객의 질문을 간략히 요약하고 답변을 제공해줘:
    참고 문서: {related_document}
    
    질문: {question}
    
    고객에게 제공할 답변을 작성해줘:
    """
    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=500,
        temperature=0.5
    )
    answer = response.choices[0].message['content'].strip()

    # 4. 장기 기억을 위한 추가 prompt 생성
    memory_prompt = f"""
    너는 이전에 아래와 같은 질문과 답변을 제공한 적이 있어:
    질문: {question}
    답변: {answer}
    이 정보는 앞으로도 유사한 질문을 처리할 때 기억해야 할 중요한 내용이야.
    """
    openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[{"role": "system", "content": memory_prompt}],
        max_tokens=200,
        temperature=0.3
    )

    return answer, question, keywords, related_document


