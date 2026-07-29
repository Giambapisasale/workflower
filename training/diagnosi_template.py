"""Perché il chat template di FunctionGemma rifiuta i nostri messages?"""

import json

from transformers import AutoTokenizer

tok = AutoTokenizer.from_pretrained("google/functiongemma-270m-it")
print("=== chat template (primi 1500 char) ===")
print((tok.chat_template or "")[:1500])
print("\n=== ruoli citati nel template ===")
template = tok.chat_template or ""
for ruolo in ("system", "user", "assistant", "tool", "function"):
    print(f"  {ruolo:10s} {template.count(ruolo)}")

esempio = json.loads(open("sft.jsonl", encoding="utf-8").readline())
strumenti = [t["function"] for t in esempio["tools"]]

prove = [
    ("solo user", [{"role": "user", "content": "ciao"}]),
    ("system+user", [{"role": "system", "content": "s"}, {"role": "user", "content": "u"}]),
    (
        "system x2 + user",
        [
            {"role": "system", "content": "s1"},
            {"role": "system", "content": "s2"},
            {"role": "user", "content": "u"},
        ],
    ),
    (
        "user + assistant tool_call",
        [
            {"role": "user", "content": "u"},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {"type": "function", "function": {"name": "ocr_pdf", "arguments": "{}"}}
                ],
            },
        ],
    ),
    (
        "user + assistant + tool",
        [
            {"role": "user", "content": "u"},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {"type": "function", "function": {"name": "ocr_pdf", "arguments": "{}"}}
                ],
            },
            {"role": "tool", "tool_call_id": "c1", "content": "ok"},
        ],
    ),
    ("i nostri messages", esempio["messages"]),
]

print("\n=== prove ===")
for etichetta, messaggi in prove:
    for con_tool in (True, False):
        try:
            reso = tok.apply_chat_template(
                messaggi,
                tools=strumenti if con_tool else None,
                tokenize=False,
                add_generation_prompt=True,
            )
            print(f"  OK   {etichetta:28s} tools={con_tool}  -> {len(reso)} char")
        except Exception as exc:  # noqa: BLE001
            print(f"  KO   {etichetta:28s} tools={con_tool}  {type(exc).__name__}: "
                  f"{str(exc)[:110]}")

print("\n=== rendering di una conversazione minima con tool (se possibile) ===")
try:
    reso = tok.apply_chat_template(
        [{"role": "user", "content": "leggi il documento"}],
        tools=strumenti,
        tokenize=False,
        add_generation_prompt=True,
    )
    print(reso[:1200])
except Exception as exc:  # noqa: BLE001
    print("KO:", exc)
