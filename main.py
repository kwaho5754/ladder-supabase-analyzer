from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
from supabase import create_client, Client
from dotenv import load_dotenv
import os
from collections import Counter

load_dotenv()

app = Flask(__name__)
CORS(app)

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
SUPABASE_TABLE = os.environ.get("SUPABASE_TABLE", "ladder")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

def convert(entry):
    side = '좌' if entry['start_point'] == 'LEFT' else '우'
    count = str(entry['line_count'])
    oe = '짝' if entry['odd_even'] == 'EVEN' else '홀'
    return f"{side}{count}{oe}"

def parse_block(s):
    return s[0], s[1:-1], s[-1]

def flip_full(block):
    return [('우' if s == '좌' else '좌') + c + ('짝' if o == '홀' else '홀') for s, c, o in map(parse_block, block)]

def find_all_matches(block, full_data):
    matches = []
    block_len = len(block)

    for i in reversed(range(len(full_data) - block_len)):
        candidate = full_data[i:i + block_len]
        if candidate == block:
            top_index = i - 1
            if 0 <= top_index < len(full_data):
                matches.append(full_data[top_index])

    return matches[:10]  # 상위 10개 예측값만 수집

@app.route("/")
def home():
    return send_from_directory(os.path.dirname(__file__), "index.html")

@app.route("/predict_top3_summary")
def predict_top3_summary():
    try:
        response = supabase.table(SUPABASE_TABLE) \
            .select("*") \
            .order("reg_date", desc=True) \
            .order("date_round", desc=True) \
            .limit(5000) \
            .execute()

        raw = response.data
        all_data = [convert(d) for d in raw]

        block = all_data[:3]  # 3줄 블럭로 변경
        flow = block  # 정방향만 사용

        predictions = find_all_matches(flow, all_data)

        valid_values = {"좌3홀", "좌3짝", "우3홀", "우3짝"}
        filtered = [p for p in predictions if p in valid_values]

        if len(set(filtered)) < 4:
            return jsonify({"예측 그룹 (3/4)": [], "제외값": "부족", "설명": "데이터 부족"})

        counter = Counter(filtered)
        excluded = min(counter.items(), key=lambda x: x[1])[0]
        group = [k for k in counter if k != excluded]

        result = {
            "예측 그룹 (3/4)": [f"{k} ({counter[k]}회)" for k in group],
            "제외값": f"{excluded} ({counter[excluded]}회)",
            "설명": "3줄 블럭 기준 정방향 흐름 기반 예측"
        }

        return jsonify(result)

    except Exception as e:
        return jsonify({"error": str(e)})

if __name__ == '__main__':
    port = int(os.environ.get("PORT") or 5000)
    app.run(host='0.0.0.0', port=port)
