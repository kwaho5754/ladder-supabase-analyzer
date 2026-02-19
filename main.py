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

def _calc_stats(matches):
    """matches: [{순번: int or '❌', ...}]"""
    nums = [int(m["순번"]) for m in matches if str(m.get("순번", "")).isdigit()]
    return {
        "전체매칭수": len(nums),
        "최대순번": max(nums) if nums else None,
        "최소순번": min(nums) if nums else None,
    }

def find_all_matches(block, full_data):
    """
    - full_data(최근순 정렬된 데이터)에서 block과 완전히 동일한 구간을 모두 찾음
    - 화면에는 '최근(순번 작은 것)' 기준 Top5만 보여주되,
      응답에 전체 매칭 수/최대 순번을 함께 내려서 리밋/범위 이슈를 확실히 검증 가능하게 함
    """
    top_matches_all = []
    bottom_matches_all = []
    block_len = len(block)

    # ✅ 마지막 시작 위치 누락 방지: +1
    for i in reversed(range(len(full_data) - block_len + 1)):
        candidate = full_data[i:i + block_len]
        if candidate == block:
            top_index = i - 1
            top_pred = full_data[top_index] if top_index >= 0 else "❌ 없음"
            top_matches_all.append({
                "값": top_pred,
                "블럭": ">".join(block),
                "순번": i + 1
            })

            bottom_index = i + block_len
            bottom_pred = full_data[bottom_index] if bottom_index < len(full_data) else "❌ 없음"
            bottom_matches_all.append({
                "값": bottom_pred,
                "블럭": ">".join(block),
                "순번": i + 1
            })

    # 통계는 "전체 매칭" 기준으로 계산
    top_stats = _calc_stats(top_matches_all)
    bottom_stats = _calc_stats(bottom_matches_all)

    # 표시용(최근부터) Top5: 순번 작은 것(최근) 우선
    if not top_matches_all:
        top_display = [{"값": "❌ 없음", "블럭": ">".join(block), "순번": "❌"}]
    else:
        top_display = sorted(
            top_matches_all,
            key=lambda x: int(x["순번"]) if str(x["순번"]).isdigit() else 999999999
        )[:5]

    if not bottom_matches_all:
        bottom_display = [{"값": "❌ 없음", "블럭": ">".join(block), "순번": "❌"}]
    else:
        bottom_display = sorted(
            bottom_matches_all,
            key=lambda x: int(x["순번"]) if str(x["순번"]).isdigit() else 999999999
        )[:5]

    return top_display, bottom_display, top_stats, bottom_stats

@app.route("/")
def home():
    return send_from_directory(os.path.dirname(__file__), "index.html")

@app.route("/predict")
def predict():
    try:
        mode = request.args.get("mode", "3block_orig")
        size = int(mode[0])

        response = supabase.table(SUPABASE_TABLE) \
            .select("*") \
            .order("reg_date", desc=True) \
            .order("date_round", desc=True) \
            .limit(10000) \
            .execute()

        raw = response.data
        if not raw:
            return jsonify({"error": "데이터가 없습니다."})

        round_num = int(raw[0]["date_round"]) + 1
        all_data = [convert(d) for d in raw]
        recent_flow = all_data[:size]

        if "flip_full" in mode:
            flow = flip_full(recent_flow)
        elif "flip_start" in mode:
            flow = flip_start(recent_flow)
        elif "flip_odd_even" in mode:
            flow = flip_odd_even(recent_flow)
        else:
            flow = recent_flow

        top, bottom, top_stats, bottom_stats = find_all_matches(flow, all_data)

        return jsonify({
            "예측회차": round_num,

            # ✅ 리밋이 진짜 적용됐는지 증거
            "조회건수": len(raw),

            # ✅ '왜 900대에서 멈춰 보이냐'를 증거로 확인
            "상단_전체매칭수": top_stats["전체매칭수"],
            "상단_최대순번": top_stats["최대순번"],
            "상단_최소순번": top_stats["최소순번"],

            "하단_전체매칭수": bottom_stats["전체매칭수"],
            "하단_최대순번": bottom_stats["최대순번"],
            "하단_최소순번": bottom_stats["최소순번"],

            # 표시용(최근 Top5)
            "상단값들": top,
            "하단값들": bottom
        })

    except Exception as e:
        return jsonify({"error": str(e)})

@app.route("/predict_top3_summary")
def predict_top3_summary():
    try:
        response = supabase.table(SUPABASE_TABLE) \
            .select("*") \
            .order("reg_date", desc=True) \
            .order("date_round", desc=True) \
            .limit(10000) \
            .execute()

        raw = response.data
        if not raw:
            return jsonify({"error": "데이터가 없습니다."})

        all_data = [convert(d) for d in raw]
        result = {}

        for size in [3, 4]:  # 3줄 + 4줄 블럭 포함
            recent_block = all_data[:size]
            transform_modes = {
                "flip_full": flip_full,
                "flip_start": flip_start,
                "flip_odd_even": flip_odd_even
            }

            top_values = []
            bottom_values = []

            for fn in transform_modes.values():
                flow = fn(recent_block)
                top, bottom, _, _ = find_all_matches(flow, all_data)

                top_values += [t["값"] for t in top if t.get("값") != "❌ 없음"]
                bottom_values += [b["값"] for b in bottom if b.get("값") != "❌ 없음"]

            top_counter = Counter(top_values)
            bottom_counter = Counter(bottom_values)

            result[f"{size}줄 블럭 Top3 요약"] = {
                "Top3상단": [v[0] for v in top_counter.most_common(3)],
                "Top3하단": [v[0] for v in bottom_counter.most_common(3)]
            }

        return jsonify({
            "조회건수": len(raw),
            "요약": result
        })

    except Exception as e:
        return jsonify({"error": str(e)})

if __name__ == '__main__':
    port = int(os.environ.get("PORT") or 5000)
    app.run(host='0.0.0.0', port=port)
