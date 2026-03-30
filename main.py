import argparse
import json
import re
import urllib.parse
import urllib.request
from html import unescape
from pathlib import Path

import ollama  # type: ignore

ROOT = Path(__file__).resolve().parent

SYSTEM_PROMPT = """너는 **MyAgent**라는 이름의 로컬 코딩·문서 보조 에이전트다.

[로컬 파일 시스템 Tool — 반드시 구현된 기능]
프로젝트 루트 폴더 안의 **텍스트 파일**만 다룬다 (상대 경로, UTF-8).
- **read_file(path)**: 기존 파일 내용을 통째로 읽는다. 없으면 오류 메시지.
- **write_file(path, content)**: 파일을 **새로 만들거나 전체 내용을 덮어쓴다** (mkdir 포함).
- **modify_file(path, before, after)**: 파일이 있어야 하고, 본문에서 **before**가 처음 나오는 한 곳만 **after**로 바꾼다.

파일 작업 예:
@@call: {"function":"read_file","args":{"path":"README.md"}}
@@call: {"function":"write_file","args":{"path":"notes.txt","content":"첫 줄\\n둘째 줄"}}
@@call: {"function":"modify_file","args":{"path":"notes.txt","before":"첫 줄","after":"제목"}}

[나무위키를 항상 쓰는 방식 — 기본 동작]
외부 지식·설명·배경이 필요하면 **항상 나무위키(namu.wiki)를 사용한다**고 가정하고 행동한다.
1) 사용자 문장에서 **검색에 쓸 핵심 키워드 1~2개**를 골라낸다 (고유명사, 주제어 위주).
2) 그 키워드로 **namu_search**를 호출한다.
3) 검색 결과는 시스템이 **프로젝트 폴더 안 파일**(`search_<키워드>.md` 형태)로 자동 저장한다. 저장까지가 한 세트다.
4) 그 다음 사용자에게 검색 요약과 저장된 파일 이름을 짧게 알려준다.

지식 검색은 나무위키, 메모·코드·설정 파일은 위 로컬 파일 Tool로 처리한다.

[정체성]
- 이름: MyAgent
- 말투: 한국어로 짧고 명확하게.
- 한계: 프로젝트 루트 밖 파일은 다루지 못한다.

[도구 한 줄 형식]
@@call: {"function":"함수이름","args":{...}}

- read_file: {"path": "상대경로"}
- write_file: {"path": "상대경로", "content": "전체 내용"}
- modify_file: {"path": "상대경로", "before": "...", "after": "..."}
- namu_search: {"query": "키워드", "max_chars": 1500}

지식 질문 예: 사용자가 "강남대 알려줘" → 키워드 `강남대` → 아래처럼 호출.
@@call: {"function":"namu_search","args":{"query":"강남대","max_chars":1500}}
"""

CHAT_OPTIONS = {"num_predict": 768}
MAX_TOOL_STEPS = 5


def safe_path(rel_path: str) -> Path:
    """프로젝트 루트 밖 경로는 허용하지 않음."""
    p = (ROOT / rel_path).resolve()
    if p != ROOT and ROOT not in p.parents:
        raise ValueError("path is outside project root")
    return p


def read_file(path: str) -> str:
    """로컬 텍스트 파일 읽기 (UTF-8)."""
    p = safe_path(path)
    return p.read_text(encoding="utf-8", errors="replace") if p.exists() else f"[read_file] not found: {path}"


def write_file(path: str, content: str) -> str:
    """텍스트 파일 새로 쓰기 또는 전체 덮어쓰기."""
    p = safe_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return f"[write_file] ok: {path}"


def modify_file(path: str, before: str, after: str) -> str:
    """기존 내용에서 before → after 치환(첫 1회만)."""
    p = safe_path(path)
    if not p.exists():
        return f"[modify_file] not found: {path}"
    text = p.read_text(encoding="utf-8", errors="replace")
    if before not in text:
        return "[modify_file] before not found"
    p.write_text(text.replace(before, after, 1), encoding="utf-8")
    return f"[modify_file] ok: {path}"


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "myagent/0.1"}, method="GET")
    with urllib.request.urlopen(req, timeout=15) as resp:
        return resp.read().decode("utf-8", errors="replace")


def strip_html(html: str) -> str:
    html = re.sub(r"<script[^>]*>.*?</script>", " ", html, flags=re.S | re.I)
    html = re.sub(r"<style[^>]*>.*?</style>", " ", html, flags=re.S | re.I)
    html = re.sub(r"<[^>]+>", " ", html)
    html = unescape(html)
    return re.sub(r"\s+", " ", html).strip()


def namu_search(query: str, max_chars: int = 1500) -> str:
    query = (query or "").strip()
    if not query:
        return "[namu_search] query is empty"
    search_url = "https://namu.wiki/Search?q=" + urllib.parse.quote(query)
    try:
        html = fetch(search_url)
    except Exception as e:
        return f"[namu_search] failed: {e}"
    candidates = re.findall(r'href="/w/([^"?#]+)"', html)
    title = urllib.parse.unquote(candidates[0]) if candidates else query
    article_url = "https://namu.wiki/w/" + candidates[0] if candidates else search_url
    text = strip_html(html)[:max_chars]
    return f"[namu.wiki]\n{title}\n{text}\n\n{article_url}"


TOOLS = {
    "read_file": read_file,
    "write_file": write_file,
    "modify_file": modify_file,
    "namu_search": namu_search,
}


def safe_filename(text: str) -> str:
    return re.sub(r'[<>:"/\\|?*\s]+', "_", text).strip("_") or "search_result"


def parse_call(text: str) -> dict | None:
    if "@@call:" not in text:
        return None
    chunk = text.split("@@call:", 1)[1]
    s, e = chunk.find("{"), chunk.rfind("}")
    if s < 0 or e <= s:
        return None
    try:
        return json.loads(chunk[s : e + 1])
    except Exception:
        return None


def run_tool(call: dict) -> tuple[str, str]:
    fn = call.get("function")
    args = call.get("args") or {}
    if fn not in TOOLS:
        return fn or "", f"[tool] unknown: {fn}"
    try:
        return fn, TOOLS[fn](**args)
    except Exception as e:
        return fn, f"[tool error] {e}"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="qwen2.5-coder:7b")
    args = parser.parse_args()

    messages: list[dict[str, str]] = [{"role": "system", "content": SYSTEM_PROMPT}]

    while True:
        try:
            user = input("you> ").strip()
        except (KeyboardInterrupt, EOFError):
            return
        if not user:
            continue

        messages.append({"role": "user", "content": user})
        auto_saved = False

        for _ in range(MAX_TOOL_STEPS):
            resp = ollama.chat(
                model=args.model,
                messages=messages,
                options=CHAT_OPTIONS,
            )
            assistant = resp["message"]["content"]
            call = parse_call(assistant)

            if not call:
                print(assistant)
                messages.append({"role": "assistant", "content": assistant})
                break

            messages.append({"role": "assistant", "content": assistant})
            fn, result = run_tool(call)
            messages.append({"role": "user", "content": "TOOL_RESULT:\n" + result})

            if fn == "namu_search" and not auto_saved:
                q = str((call.get("args") or {}).get("query", "search"))
                out = f"search_{safe_filename(q)}.md"
                save = write_file(out, result)
                auto_saved = True
                messages.append({"role": "user", "content": "TOOL_RESULT:\n" + save + "\nSaved: " + out})


if __name__ == "__main__":
    main()
