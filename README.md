# myagent

Ollama 로컬 LLM + **시스템 프롬프트**로 터미널에서 동작하는 에이전트입니다.

- 프로젝트 폴더 안 **텍스트 파일** 읽기 / 쓰기 / 수정  
- **나무위키**(namu.wiki) 검색  
- **한 번의 질문**에 대해 **Tool을 2번 이상 연속**으로 호출하는 구조  

---

## 준비물

- Python 3.10 이상  
- [Ollama](https://ollama.com) 설치, 사용할 모델 받기 (예: `ollama pull qwen2.5-coder:7b`)  
- `pip install ollama` 또는 `uv sync`  

---

## 실행

```powershell
cd "프로젝트경로\myagent"
python -m pip install ollama
python main.py --model qwen2.5-coder:7b
```

`ollama list`에 있는 모델 이름을 `--model`에 맞추면 됩니다. 종료는 **Ctrl+C**입니다.

`uv` 사용 시:

```powershell
uv sync
uv run python main.py --model qwen2.5-coder:7b
```


### 유저의 한 번 질문에 대해 2번 이상의 Tool을 연속으로 호출하는 로직 

 **연속 Tool**을 기능 원리 입니다 

**1) Chaining (이전 Tool 결과 → 다음 Tool 입력)**

- LLM이 이전에 받은 `TOOL_RESULT` 텍스트를 보고, 다음 `@@call`의 `args`를 채웁니다.  
  (예: `read_file` 결과를 바탕으로 `write_file` 내용을 정함.)  
- `namu_search` 뒤에는 프로그램이 검색 문자열을 `write_file`에 넘겨 **자동으로** 저장 단계를 이어 붙입니다.

**2) tool_calls 파싱 + 루프**

- OpenAI 스타일 `tool_calls` 필드 대신, 응답 문자열 안의 **`@@call: { JSON }`** 한 줄을 `parse_call()`로 파싱합니다.  
- 파싱되면 도구를 실행하고, 결과를 메시지에 넣은 뒤 **같은 질문**에 대해 루프를 계속 돕니다.

**3) Tool 결과를 컨텍스트로 유지**

- `messages`에 사용자·어시스턴트·`TOOL_RESULT`가 쌓이므로, 다음 `ollama.chat` 호출에서 LLM이 **이전 도구 결과**를 보고 다음 행동을 고릅니다.

---

## 동작 흐름 (요약)

1. `you>` 에 질문 입력  
2. `messages`에 사용자 문장 추가 → `ollama.chat`  
3. 응답에 `@@call`이 있으면 → 해당 함수 실행 → 결과를 `TOOL_RESULT`로 `messages`에 추가  
4. 3을 **같은 질문**에 대해 최대 `MAX_TOOL_STEPS`번까지 반복  
5. `@@call`이 없으면 일반 텍스트를 출력하고, 다시 1로  

도구 이름과 실제 함수는 `main.py`의 `TOOLS`에 연결되어 있습니다.

---

## 제공 도구

| 기능 | 함수 | 비고 |
|------|------|------|
| 읽기 | `read_file` | 프로젝트 루트 안 상대 경로 |
| 쓰기 | `write_file` | 새로 쓰기 / 전체 덮어쓰기 |
| 수정 | `modify_file` | `before` → `after` 한 번만 치환 |
| 나무위키 | `namu_search` | 검색 페이지 HTML → 짧은 요약 텍스트 |

LLM이 출력하는 형식 (한 줄):

```text
@@call: {"function":"read_file","args":{"path":"README.md"}}
```

---

## 나무위키 검색 후

- 긴 본문은 터미널에 모두 출력하지 않고 **`search_<키워드>.md`** 로 저장합니다.  
- 짧은 안내만 출력한 뒤 다시 `you>` 로 돌아가 다음 질문을 받을 수 있습니다.

---

## 보안

`safe_path()`로 **프로젝트 루트 밖** 경로는 열 수 없게 막았습니다.

---

## 프로젝트 파일

| 파일 | 설명 |
|------|------|
| `main.py` | 에이전트 루프, 도구, Ollama 연동 |
| `pyproject.toml`, `uv.lock` | uv 의존성 |
| `.gitignore` | `.venv` 등 제외 |

---

## 문제 해결

- **`model ... not found`**: `ollama list`로 이름 확인 후 `--model` 맞추기 또는 `ollama pull`.  
- **느림**: 로컬 LLM 추론·첫 로딩 시간은 PC/모델에 따라 다릅니다.
