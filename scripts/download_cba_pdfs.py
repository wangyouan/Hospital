#!/usr/bin/env python3
"""
download_cba_pdfs.py — 全量下载 Cornell eCommons CBA PDF
可反复运行，断点续跑。

DSpace 7 REST API:
  GET /core/items/{uuid}/bundles         → 找 ORIGINAL bundle
  GET /core/bundles/{bundle_uuid}/bitstreams → 列 bitstream
  GET /core/bitstreams/{bs_uuid}/content     → 下载 PDF
"""

import csv
import hashlib
import os
import sys
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

# ── 配置 ──────────────────────────────────────────────────
API = "https://ecommons.cornell.edu/server/api"
DST = "/data/disk4/workspace/projects/hospital/data/cba"
PDF_DIR = os.path.join(DST, "pdfs")
DONE_FILE = os.path.join(DST, "done.txt")
FAIL_FILE = os.path.join(DST, "download_failures.log")
MAP_FILE = os.path.join(DST, "bitstream_map.csv")
MANIFEST = os.path.join(DST, "cba_manifest_full.csv")

HEADERS = {
    "Accept": "application/json",
    "User-Agent": "hospital-research/1.0 (academic; wangyouan)",
}

MAX_WORKERS = 4
CHECKPOINT_INTERVAL = 200
RETRY_BASE_SLEEP = 2
MAX_RETRIES = 5
REQUEST_SLEEP = 0.3  # 每个子请求间的 sleep

# ── 线程安全写锁 ──────────────────────────────────────────
write_lock = threading.Lock()


def get_json(url, tries=MAX_RETRIES):
    """带指数退避的 GET JSON，失败返回 None"""
    for i in range(tries):
        try:
            r = requests.get(url, headers=HEADERS, timeout=(15, 90))
            if r.status_code == 200:
                return r.json()
            if r.status_code in (429, 500, 502, 503, 504):
                wait = RETRY_BASE_SLEEP * (2 ** i)
                time.sleep(wait)
                continue
            # 4xx (非 429) 不重试
            if 400 <= r.status_code < 500:
                return None
        except requests.RequestException:
            wait = RETRY_BASE_SLEEP * (2 ** i)
            time.sleep(wait)
    return None


def iter_paged(url):
    """遍历 DSpace 分页，yield 每个 _embedded 条目"""
    seen = set()
    while url:
        if url in seen:
            break  # 防止无限循环
        seen.add(url)
        j = get_json(url)
        if j is None:
            return
        emb = j.get("_embedded")
        if emb:
            # _embedded 只含一个 key（如 "bundles", "bitstreams"）
            key = next(iter(emb), None)
            if key:
                items = emb[key]
                if isinstance(items, list):
                    for it in items:
                        yield it
        # 下一页
        links = j.get("_links", {})
        next_link = links.get("next", {}) if isinstance(links, dict) else {}
        url = next_link.get("href") if isinstance(next_link, dict) else None
        if url:
            time.sleep(0.1)  # 分页间小 sleep


def download_file(url, dest_path, tries=MAX_RETRIES):
    """下载文件到 dest_path，校验 >1KB，返回 (success, file_size)"""
    for i in range(tries):
        try:
            r = requests.get(
                url,
                headers={"User-Agent": HEADERS["User-Agent"]},
                timeout=(15, 180),
                stream=True,
            )
            if r.status_code == 200:
                with open(dest_path, "wb") as f:
                    for chunk in r.iter_content(16384):
                        if chunk:
                            f.write(chunk)
                sz = os.path.getsize(dest_path)
                if sz <= 1024:
                    os.remove(dest_path)
                    return False, f"file too small ({sz} bytes)"
                return True, sz
            if r.status_code in (429, 500, 502, 503, 504):
                wait = RETRY_BASE_SLEEP * (2 ** i)
                time.sleep(wait)
                continue
            return False, f"HTTP {r.status_code}"
        except requests.RequestException as e:
            wait = RETRY_BASE_SLEEP * (2 ** i)
            time.sleep(wait)
    return False, "max retries exceeded"


def compute_sha256(filepath):
    """计算文件 SHA256"""
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


# ── 核心：下载单个 item ──────────────────────────────────
def download_item(item_uuid):
    """
    下载一个 item 的所有 PDF bitstream。
    返回 (item_uuid, saved_list, error_list)
    saved_list: [(bitstream_uuid, filename, local_path, size, sha256), ...]
    error_list: [(stage, error_msg), ...]

    若 item 无 ORIGINAL bundle 或无 PDF，返回空 saved_list 且不报错。
    """
    saved = []
    errors = []

    # Step 1: 获取 bundles
    bundles = list(iter_paged(f"{API}/core/items/{item_uuid}/bundles"))
    if not bundles:
        errors.append(("bundles", "no bundles returned (API may have failed)"))
        return item_uuid, saved, errors

    time.sleep(REQUEST_SLEEP)

    # 找 ORIGINAL bundle
    orig_bundles = [b for b in bundles if b.get("name") == "ORIGINAL"]
    if not orig_bundles:
        # 无 ORIGINAL 包不一定是错误（有些 item 只有 metadata）
        return item_uuid, saved, errors

    for bundle in orig_bundles:
        bundle_uuid = bundle.get("uuid")
        if not bundle_uuid:
            continue

        # Step 2: 获取 bitstreams
        bs_url = bundle.get("_links", {}).get("bitstreams", {}).get("href")
        if not bs_url:
            continue

        bitstreams = list(iter_paged(bs_url))
        time.sleep(REQUEST_SLEEP)

        for bs in bitstreams:
            mime = (bs.get("mimeType") or "").lower()
            name = (bs.get("name") or "")
            bs_uuid = bs.get("uuid")
            if not bs_uuid:
                continue

            # 只下载 PDF
            if "pdf" not in mime and not name.lower().endswith(".pdf"):
                continue

            content_url = bs.get("_links", {}).get("content", {}).get("href")
            if not content_url:
                errors.append((f"bitstream/{bs_uuid}", "no content link"))
                continue

            # 输出路径
            outdir = os.path.join(PDF_DIR, item_uuid)
            os.makedirs(outdir, exist_ok=True)
            outpath = os.path.join(outdir, f"{bs_uuid}.pdf")

            # 已存在且有效 → 复用
            if os.path.exists(outpath) and os.path.getsize(outpath) > 1024:
                sz = os.path.getsize(outpath)
                sha = compute_sha256(outpath)
                saved.append((bs_uuid, name, outpath, sz, sha))
                continue

            # 下载
            ok, info = download_file(content_url, outpath)
            time.sleep(REQUEST_SLEEP)

            if ok:
                sz = info
                sha = compute_sha256(outpath)
                saved.append((bs_uuid, name, outpath, sz, sha))
            else:
                errors.append((f"download/{bs_uuid}", info))
                # 删掉可能残留的损坏文件
                if os.path.exists(outpath):
                    try:
                        os.remove(outpath)
                    except OSError:
                        pass

    return item_uuid, saved, errors


# ── 进度文件管理 ──────────────────────────────────────────
def load_done():
    """加载已完成 item uuid 集合"""
    if not os.path.exists(DONE_FILE):
        return set()
    with open(DONE_FILE) as f:
        return {line.strip() for line in f if line.strip()}


def mark_done(uuid):
    """追加一个 completed uuid 到 done.txt，立即 flush"""
    # 线程安全：统一由主线程调用，无需锁
    with open(DONE_FILE, "a") as f:
        f.write(uuid + "\n")
        f.flush()
        os.fsync(f.fileno())


def log_failure(uuid, errors):
    """追加失败记录"""
    with write_lock:
        with open(FAIL_FILE, "a") as f:
            for stage, err in errors:
                f.write(f"{uuid}\t{stage}\t{err}\t{time.strftime('%F %T')}\n")
            f.flush()


def append_map(uuid, saved):
    """追加 bitstream 映射记录"""
    with write_lock:
        with open(MAP_FILE, "a") as f:
            for bs_uuid, name, path, sz, sha in saved:
                f.write(f"{uuid},{bs_uuid},{name},{sz},pdf,{sha}\n")
            f.flush()


# ── 主流程 ────────────────────────────────────────────────
def main():
    # 加载 manifest
    if not os.path.exists(MANIFEST):
        print(f"ERROR: manifest not found: {MANIFEST}")
        sys.exit(1)

    with open(MANIFEST) as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    done = load_done()
    todo = [r["uuid"] for r in rows if r["uuid"] not in done]

    print(f"total={len(rows)}  done={len(done)}  todo={len(todo)}")

    if not todo:
        print("All items already downloaded. Nothing to do.")
        return

    # 初始化输出文件（不存在时写 header）
    if not os.path.exists(MAP_FILE):
        with open(MAP_FILE, "w") as f:
            f.write("item_uuid,bitstream_uuid,orig_filename,bytes,mime,sha256\n")

    # 统计
    n_ok = 0
    n_fail = 0
    n_no_pdf = 0  # 无 ORIGINAL bundle 或无 PDF 的 item
    start_time = time.time()

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(download_item, u): u for u in todo}

        for i, fut in enumerate(as_completed(futures), 1):
            u = futures[fut]
            try:
                item_uuid, saved, errors = fut.result()

                if saved:
                    append_map(item_uuid, saved)
                    mark_done(item_uuid)
                    n_ok += 1
                elif not errors:
                    # 无 ORIGINAL bundle 或无 PDF — 视为完成（无需重试）
                    mark_done(item_uuid)
                    n_no_pdf += 1
                else:
                    log_failure(item_uuid, errors)
                    n_fail += 1

            except Exception as e:
                log_failure(u, [("futures", repr(e))])
                n_fail += 1

            # 进度报告
            if i % CHECKPOINT_INTERVAL == 0:
                elapsed = time.time() - start_time
                rate = i / elapsed if elapsed > 0 else 0
                eta = (len(todo) - i) / rate if rate > 0 else 0
                print(
                    f"[{i}/{len(todo)}] "
                    f"ok={n_ok} no_pdf={n_no_pdf} fail={n_fail} "
                    f"rate={rate:.1f}/s ETA={eta/60:.0f}min"
                )

    elapsed = time.time() - start_time
    print(f"\n=== DONE ===")
    print(f"ok={n_ok}  no_pdf={n_no_pdf}  fail={n_fail}")
    print(f"elapsed={elapsed/60:.1f}min  "
          f"rate={len(todo)/elapsed:.2f}/s")

    # 末次统计文件
    done_final = load_done()
    print(f"done.txt lines: {len(done_final)}")

    if os.path.exists(MAP_FILE):
        with open(MAP_FILE) as f:
            map_lines = sum(1 for _ in f) - 1  # 减 header
        print(f"bitstream_map.csv rows: {map_lines}")

    if os.path.exists(FAIL_FILE):
        with open(FAIL_FILE) as f:
            fail_lines = sum(1 for _ in f)
        print(f"download_failures.log lines: {fail_lines}")


if __name__ == "__main__":
    main()
