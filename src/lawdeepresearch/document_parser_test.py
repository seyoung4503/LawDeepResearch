# pip install requests
import os
import requests
from dotenv import load_dotenv

load_dotenv()
# api_key = "up_PDWNPAeUnlF1LIm16ox503FNRmERJ"

api_key = os.getenv("UPSTAGE_API_KEY")
filename = "주택임대차표준계약서_test.pdf"

url = "https://api.upstage.ai/v1/document-digitization"
headers = {"Authorization": f"Bearer {api_key}"}
files = {"document": open(filename, "rb")}
data = {"ocr": "force", "model": "document-parse"}
response = requests.post(url, headers=headers, files=files, data=data)

print(response.json())

# if response.status_code == 200:
#     result_json = response.json()

#     # 'elements' 키가 있는지 확인하고, 리스트를 순회하며 텍스트만 추출
#     if "elements" in result_json:
#         for element in result_json["elements"]:
#             # 각 element 안에 'content'와 'text' 키가 있는지 확인
#             if "content" in element and "text" in element["content"]:
#                 text = element["content"]["text"]
#                 print(text)  # 추출한 텍스트 출력
#     else:
#         print("결과에 'elements' 키를 찾을 수 없습니다.")

# else:
#     print(f"API 요청 실패: {response.status_code}")
#     print(response.text)
