# myagent

Ollama + 로컬 파일 / 나무위키 검색 툴.

## 실행

```powershell
cd "c:\Users\최소미\Desktop\4\web\myagent"
python -m pip install ollama
python main.py --model qwen2.5-coder:7b
```

종료: `Ctrl+C`

## 기능 (3가지)

1. **파일 툴** (로컬 텍스트, 프로젝트 폴더만)  
   - `read_file(path)` — 읽기  
   - `write_file(path, content)` — 새로 쓰기·전체 덮어쓰기  
   - `modify_file(path, before, after)` — 문자열 한 번 치환
2. **나무위키** — `namu_search(query)` → `https://namu.wiki/Search?q=...` 결과 요약
3. **연속 툴** — LLM이 `@@call: {...}` 로 호출; `namu_search` 후 자동으로 `search_<키워드>.md` 저장

모델은 `ollama list`에 있는 이름으로 `--model` 지정.
