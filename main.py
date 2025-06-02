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

def flip_start(block):
    return [s + ('4' if c == '3' else '3') + ('홀' if o == '짝' else '짝') for s, c, o in map(parse_block, block)]

def flip_odd_even(block):
    return [('우' if s == '좌' else '좌') + ('4' if c == '3' else '3') + o for s, c, o in map(parse_block, block)]

def find_all_matches(block, full_data):
    top_matches = []
    bottom_matches = []
    block_len = len(block)

    for i in reversed(range(len(full_data) - block_len)):
        candidate = full_data[i:i + block_len]
        if candidate == block:
            top_index = i - 1
            top_pred = full_data[top_index] if top_index >= 0 else "❌ 없음"
            top_matches.append({
                "값": top_pred,
                "블럭": ">".join(block),
                "순번": i + 1
            })

            bottom_index = i + block_len
            bottom_pred = full_data[bottom_index] if bottom_index < len(full_data) else "❌ 없음"
            bottom_matches.append({
                "값": bottom_pred,
                "블럭": ">".join(block),
                "순번": i + 1
            })

    if not top_matches:
        top_matches.append({"값": "❌ 없음", "블럭": ">".join(block), "순번": "❌"})
    if not bottom_matches:
        bottom_matches.append({"값": "❌ 없음", "블럭": ">".join(block), "순번": "❌"})

    top_matches = sorted(top_matches, key=lambda x: int(x["순번"]) if str(x["순번"]).isdigit() else 99999)[:5]
    bottom_matches = sorted(bottom_matches, key=lambda x: int(x["순번"]) if str(x["순번"]).isdigit() else 99999)[:5]

    return top_matches, bottom_matches

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
            .limit(3000) \
            .execute()

        raw = response.data
        all_data = [convert(d) for d in raw]

        transform_modes = {
            "flip_full": flip_full,
            "flip_start": flip_start,
            "flip_odd_even": flip_odd_even
        }

        valid_values = {"좌3홀", "좌3짝", "우3홀", "우3짝"}
        summary_result = {}

        def analyze(size):
            recent_block = all_data[:size]
            top_values = []

            for fn in transform_modes.values():
                flow = fn(recent_block)
                top, _ = find_all_matches(flow, all_data)
                top_values += [t["값"] for t in top if t["값"] in valid_values]

            counter = Counter(top_values)
            total = sum(counter.values())
            if len(counter) < 4 or total == 0:
                return {
                    "예측그룹(3/4)": [],
                    "❌ 제외값": "❌ 부족",
                    "총합": 0,
                    "설명": "데이터 부족"
                }

            excluded = min(counter.items(), key=lambda x: x[1])[0]
            filtered = {k: v for k, v in counter.items() if k != excluded}
            sorted_top3 = sorted(filtered.items(), key=lambda x: x[1], reverse=True)
            group = [f"{k}({round(v / total * 100)}%)" for k, v in sorted_top3]
            excluded_ratio = f"{excluded}({round(counter[excluded] / total * 100)}%)"

            max_ratio = max(filtered.values()) / total
            comment = "편중 경향 있음" if max_ratio >= 0.5 else "분산되어 안정적"

            return {
                "예측그룹(3/4)": group,
                "❌ 제외값": excluded_ratio,
                "총합": total,
                "설명": comment
            }

        result_3 = analyze(3)
        result_4 = analyze(4)

        final_comment = "3줄 블럭이 더 우세합니다" if result_3["총합"] > result_4["총합"] else "4줄 블럭이 더 우세합니다"
        if result_3["총합"] == result_4["총합"]:
            final_comment = "두 블럭 흐름이 비슷합니다"

        return jsonify({
            "3줄 블럭 요약": {
                "예측그룹(3/4)": result_3["예측그룹(3/4)"],
                "❌ 제외값": result_3["❌ 제외값"],
                "설명": result_3["설명"]
            },
            "4줄 블럭 요약": {
                "예측그룹(3/4)": result_4["예측그룹(3/4)"],
                "❌ 제외값": result_4["❌ 제외값"],
                "설명": result_4["설명"]
            },
            "비교 결과": final_comment
        })

    except Exception as e:
        return jsonify({"error": str(e)})

if __name__ == '__main__':
    port = int(os.environ.get("PORT") or 5000)
    app.run(host='0.0.0.0', port=port)
