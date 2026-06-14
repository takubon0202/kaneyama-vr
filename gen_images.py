#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
index.html から商品リストを抽出し、Codex CLI 組み込みの image_gen (gpt-image-2) で
各商品の EC サムネ画像を images/<売場id>_<番号>.png に生成する。
- API キーは使わない（Codex の image_gen をそのまま使う）
- 既に生成済みのファイルはスキップ（中断しても再開可能）
- 並列度 CONCURRENCY で実行
"""
import os, re, subprocess, sys, time
from concurrent.futures import ThreadPoolExecutor, as_completed

PWD = os.path.dirname(os.path.abspath(__file__))
HTML = os.path.join(PWD, "index.html")
IMGDIR = os.path.join(PWD, "images")
LOG = os.path.join(PWD, "gen_images.log")
CONCURRENCY = int(os.environ.get("GEN_CONCURRENCY", "10"))
os.makedirs(IMGDIR, exist_ok=True)

def log(msg):
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")

# ---- index.html から (id, cornerName, idx, name, desc) を抽出 ----
def parse_products():
    text = open(HTML, encoding="utf-8").read()
    m = re.search(r"const CORNERS=\[(.*?)\n\];", text, re.S)
    body = m.group(1)
    products = []
    cur_id = cur_corner = None
    idx = 0
    for line in body.splitlines():
        zm = re.search(r"Z\('([a-z0-9]+)','([^']*)'", line)
        if zm:
            cur_id, cur_corner = zm.group(1), zm.group(2)
            idx = 0
            continue
        if re.match(r"\s*P\(", line):
            toks = re.findall(r"'((?:[^'\\]|\\.)*)'", line)
            # toks[0]='' (旧アイコン), toks[1]=商品名, toks[2]=説明
            name = toks[1] if len(toks) > 1 else ""
            desc = toks[2] if len(toks) > 2 else ""
            products.append((cur_id, cur_corner, idx, name, desc))
            idx += 1
    return products

def gen_one(p):
    cid, corner, idx, name, desc = p
    target = os.path.join(IMGDIR, f"{cid}_{idx}.png")
    if os.path.exists(target) and os.path.getsize(target) > 1000:
        return (target, "skip")
    prompt = (
        "組み込みの image_gen ツールを直接使い、API キーやスクリプトは一切書かずに画像を1枚だけ生成してください。"
        f"被写体:「{name}」（{desc}。{corner}コーナーの商品）。"
        "日本のスーパーマーケットの商品・惣菜の物撮り写真。純白の背景、やや斜め上からの俯瞰、"
        "EC商品サムネイル風、自然で柔らかい照明、影は控えめ、正方形。"
        "文字・ロゴ・パッケージの文字・値札は一切入れない。リアルな写真スタイル。"
        f"生成後、画像を1024x1024にリサイズして {target} に保存し、保存先パスのみ報告してください。"
    )
    cmd = ["codex", "exec", "-m", "gpt-5.5",
           "--dangerously-bypass-approvals-and-sandbox",
           "--skip-git-repo-check", "--cd", PWD, prompt]
    try:
        subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    except subprocess.TimeoutExpired:
        return (target, "timeout")
    if os.path.exists(target) and os.path.getsize(target) > 1000:
        return (target, "ok")
    return (target, "fail")

def main():
    products = parse_products()
    todo = [p for p in products
            if not (os.path.exists(os.path.join(IMGDIR, f"{p[0]}_{p[2]}.png"))
                    and os.path.getsize(os.path.join(IMGDIR, f"{p[0]}_{p[2]}.png")) > 1000)]
    log(f"商品 {len(products)} 件 / 未生成 {len(todo)} 件 を生成開始 (並列{CONCURRENCY})")
    done = 0
    with ThreadPoolExecutor(max_workers=CONCURRENCY) as ex:
        futs = {ex.submit(gen_one, p): p for p in products}
        for fut in as_completed(futs):
            p = futs[fut]
            target, status = fut.result()
            done += 1
            log(f"[{done}/{len(products)}] {status:7s} {os.path.basename(target)}  ({p[3]})")
    log("=== 生成完了 ===")

if __name__ == "__main__":
    main()
