"""Teste local da aplicação web (sem subir servidor real)."""

from fastapi.testclient import TestClient

from meeting_processor.config import load_config
from meeting_processor.web.app import create_app


def main() -> None:
    config = load_config()
    app = create_app(config)
    client = TestClient(app)

    failures = 0

    # 1. health
    r = client.get("/api/health")
    if r.status_code == 200 and r.json()["status"] == "ok":
        print("OK  GET /api/health")
    else:
        failures += 1
        print(f"FAIL GET /api/health -> {r.status_code} {r.text[:200]}")

    # 2. listagem
    r = client.get("/api/meetings")
    if r.status_code == 200 and isinstance(r.json(), list):
        print(f"OK  GET /api/meetings ({len(r.json())} reuniões)")
    else:
        failures += 1
        print(f"FAIL GET /api/meetings -> {r.status_code}")

    # 3. página inicial (HTML)
    r = client.get("/")
    if r.status_code == 200 and "Meeting Processor" in r.text:
        print("OK  GET / (HTML)")
    else:
        failures += 1
        print(f"FAIL GET / -> {r.status_code}")

    # 4. configuração (HTML)
    r = client.get("/configuracao")
    if r.status_code == 200 and "Provedor LLM" in r.text:
        print("OK  GET /configuracao")
    else:
        failures += 1
        print(f"FAIL GET /configuracao -> {r.status_code}")

    # 4b. /settings ainda redireciona para compatibilidade
    r = client.get("/settings", follow_redirects=False)
    if r.status_code in (301, 302):
        print(f"OK  GET /settings -> redirect ({r.status_code})")
    else:
        failures += 1
        print(f"FAIL GET /settings (esperava redirect) -> {r.status_code}")

    # 5. fragmento status
    r = client.get("/fragments/status")
    if r.status_code == 200:
        print("OK  GET /fragments/status")
    else:
        failures += 1
        print(f"FAIL GET /fragments/status -> {r.status_code}")

    # 6. detalhe de reunião (se existir alguma)
    meetings = client.get("/api/meetings").json()
    if meetings:
        mid = meetings[0]["id"]
        r = client.get(f"/meetings/{mid}")
        if r.status_code == 200 and "Resumo" in r.text:
            print(f"OK  GET /meetings/{mid[:40]}...")
        else:
            failures += 1
            print(f"FAIL GET /meetings/{mid} -> {r.status_code}")
    else:
        print("--  sem reuniões no vault para testar /meetings/<id>")

    # 7. arquivo inexistente em /actions/process
    r = client.post(
        "/actions/process",
        data={"file": "C:/nao/existe/arquivo.mkv"},
        follow_redirects=False,
    )
    if r.status_code == 400:
        print("OK  POST /actions/process (arquivo inexistente -> 400)")
    else:
        failures += 1
        print(f"FAIL POST /actions/process -> {r.status_code}")

    # 8. fragmento de controles
    r = client.get("/fragments/controls")
    if r.status_code == 200 and "Watcher" in r.text and "Provedor LLM" in r.text:
        print("OK  GET /fragments/controls")
    else:
        failures += 1
        print(f"FAIL GET /fragments/controls -> {r.status_code}")

    # 9. status do watcher (JSON)
    r = client.get("/api/watcher")
    if r.status_code == 200 and "running" in r.json():
        print(f"OK  GET /api/watcher (running={r.json()['running']})")
    else:
        failures += 1
        print(f"FAIL GET /api/watcher -> {r.status_code}")

    # 10. info do LLM (JSON)
    r = client.get("/api/llm")
    body = r.json() if r.status_code == 200 else {}
    if r.status_code == 200 and body.get("provider") in ("anthropic", "local"):
        print(f"OK  GET /api/llm (provider={body['provider']})")
    else:
        failures += 1
        print(f"FAIL GET /api/llm -> {r.status_code}")

    # 11. provider inválido -> 400
    r = client.post("/actions/llm-provider", data={"provider": "gpt5"})
    if r.status_code == 400:
        print("OK  POST /actions/llm-provider (inválido -> 400)")
    else:
        failures += 1
        print(f"FAIL POST /actions/llm-provider (inválido) -> {r.status_code}")

    # 11b. Dashboard
    r = client.get("/dashboard")
    if r.status_code == 200 and "Reuniões processadas" in r.text and "kanban" not in r.text.lower()[:50]:
        print("OK  GET /dashboard (com stats)")
    else:
        failures += 1
        print(f"FAIL GET /dashboard -> {r.status_code}")

    # 11c. Kanban
    r = client.get("/tarefas")
    if r.status_code == 200 and "kanban-board" in r.text:
        print("OK  GET /tarefas (Kanban)")
    else:
        failures += 1
        print(f"FAIL GET /tarefas -> {r.status_code}")

    # 11d. Lista
    r = client.get("/tarefas?view=lista")
    if r.status_code == 200 and "Lista de tarefas" in r.text:
        print("OK  GET /tarefas?view=lista")
    else:
        failures += 1
        print(f"FAIL GET /tarefas?view=lista -> {r.status_code}")

    # 11e. API tasks
    r = client.get("/api/tasks")
    if r.status_code == 200 and isinstance(r.json(), list):
        print(f"OK  GET /api/tasks ({len(r.json())} tarefas)")
    else:
        failures += 1
        print(f"FAIL GET /api/tasks -> {r.status_code}")

    # 11f. Move task (round-trip)
    tasks = client.get("/api/tasks").json()
    if tasks:
        target = next((t for t in tasks if t["column"] == "todo"), tasks[0])
        original_col = target["column"]
        target_col = "doing" if original_col != "doing" else "todo"

        r = client.post(
            "/actions/tasks/move",
            json={
                "task_id": target["task_id"],
                "meeting_id": target["meeting_id"],
                "to_column": target_col,
            },
        )
        if r.status_code == 200 and r.json().get("ok"):
            # Verifica
            tasks2 = client.get("/api/tasks").json()
            moved = next((t for t in tasks2 if t["task_id"] == target["task_id"]), None)
            if moved and moved["column"] == target_col:
                print(f"OK  POST /actions/tasks/move ({original_col} -> {target_col})")
                # restaura
                client.post(
                    "/actions/tasks/move",
                    json={
                        "task_id": target["task_id"],
                        "meeting_id": target["meeting_id"],
                        "to_column": original_col,
                    },
                )
            else:
                failures += 1
                print(f"FAIL move não persistiu (esperado {target_col}, achou {moved['column'] if moved else 'task perdida'})")
        else:
            failures += 1
            print(f"FAIL POST /actions/tasks/move -> {r.status_code}")
    else:
        print("--  sem tarefas para testar /actions/tasks/move")

    # 11g. Delete meeting (round-trip com fake)
    from pathlib import Path
    vault_root = Path("./vault/wiki/reunioes")
    fake_id = "9999-12-31 23h59 - DELETE TEST AUTO"
    fake_dir = vault_root / fake_id
    fake_dir.mkdir(parents=True, exist_ok=True)
    (fake_dir / f"Resumo - {fake_id}.md").write_text(
        f'---\ntitle: "{fake_id}"\nsource_file: "auto-delete.mkv"\n---\n\n# Fake\n',
        encoding="utf-8",
    )
    (fake_dir / f"Tarefas - {fake_id}.md").write_text(
        "## A Fazer\n\n## Em Progresso\n\n## Concluido\n", encoding="utf-8"
    )

    # confirma que aparece
    found = any(m["id"] == fake_id for m in client.get("/api/meetings").json())
    if not found:
        failures += 1
        print("FAIL setup do delete (reunião fake não apareceu na API)")
    else:
        # DELETE via API
        r = client.delete(f"/api/meetings/{fake_id}")
        if r.status_code == 200 and r.json().get("ok"):
            still = any(m["id"] == fake_id for m in client.get("/api/meetings").json())
            if not still and not fake_dir.exists():
                print("OK  DELETE /api/meetings/{id} (pasta + API limpas)")
            else:
                failures += 1
                print(f"FAIL delete não limpou (pasta_existe={fake_dir.exists()}, na_api={still})")
        else:
            failures += 1
            print(f"FAIL DELETE /api/meetings/{{id}} -> {r.status_code}")

    # delete inexistente -> 404
    r = client.delete(f"/api/meetings/{fake_id}")
    if r.status_code == 404:
        print("OK  DELETE inexistente -> 404")
    else:
        failures += 1
        print(f"FAIL DELETE inexistente -> {r.status_code}")

    # POST do form deve redirecionar
    fake_dir.mkdir(parents=True, exist_ok=True)
    (fake_dir / f"Resumo - {fake_id}.md").write_text(
        f'---\ntitle: "{fake_id}"\n---\n', encoding="utf-8"
    )
    r = client.post(
        f"/actions/meetings/{fake_id}/delete",
        follow_redirects=False,
    )
    if r.status_code == 303 and r.headers.get("location") == "/reunioes":
        print("OK  POST /actions/meetings/{id}/delete (redirect 303 -> /reunioes)")
    else:
        failures += 1
        print(f"FAIL POST delete -> {r.status_code} loc={r.headers.get('location')}")
    # cleanup defensivo
    if fake_dir.exists():
        import shutil
        shutil.rmtree(fake_dir)

    # 11g2. Export de tarefas
    for ext, ctype, snippet in [
        ("csv", "text/csv", "status,tarefa"),
        ("json", "application/json", '"tasks"'),
        ("md",  "text/markdown", "# Tarefas exportadas"),
        ("txt", "text/plain", "TAREFAS EXPORTADAS"),
    ]:
        r = client.get(f"/api/tasks/export.{ext}")
        cd = r.headers.get("content-disposition", "")
        ct = r.headers.get("content-type", "")
        if (
            r.status_code == 200
            and snippet in r.text
            and "attachment" in cd
            and "tarefas-" in cd
            and ctype in ct
        ):
            print(f"OK  GET /api/tasks/export.{ext} ({len(r.text)} bytes)")
        else:
            failures += 1
            print(f"FAIL export.{ext} -> {r.status_code} ct={ct} cd={cd[:60]}")

    # filtro funciona em export
    r = client.get("/api/tasks/export.json?column=done")
    if r.status_code == 200 and '"count": 0' in r.text:
        print("OK  GET /api/tasks/export.json?column=done (filtro aplicado)")
    else:
        failures += 1
        print(f"FAIL export com filtro column=done -> {r.status_code}")

    # 11h. Histórico: adiciona erro fake, remove via API, e via clear-errors
    from pathlib import Path as _Path
    import json as _json
    hist_path = _Path("./vault/wiki/.processing-history.json")
    hist_backup = hist_path.read_text(encoding="utf-8") if hist_path.exists() else "[]"
    try:
        # injeta erro fake
        data = _json.loads(hist_backup)
        data.append({
            "file": "AUTO_TEST_ERR.mkv",
            "status": "error",
            "started": "2099-01-01T00:00:00",
            "completed": "2099-01-01T00:00:30",
            "details": {},
            "stage": 1,
            "error_message": "fake",
            "failed_stage": "Audio",
        })
        hist_path.write_text(_json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

        # /reunioes?filter=erros mostra
        r = client.get("/reunioes?filter=erros")
        if r.status_code == 200 and "AUTO_TEST_ERR.mkv" in r.text and "Limpar todos os erros" in r.text:
            print("OK  GET /reunioes?filter=erros (mostra erros + botões)")
        else:
            failures += 1
            print(f"FAIL /reunioes?filter=erros não mostra botões")

        # POST remove individual
        r = client.post(
            "/actions/history/remove",
            data={"file": "AUTO_TEST_ERR.mkv", "started": "2099-01-01T00:00:00"},
            follow_redirects=False,
        )
        if r.status_code == 303:
            still = "AUTO_TEST_ERR.mkv" in hist_path.read_text(encoding="utf-8")
            if not still:
                print("OK  POST /actions/history/remove")
            else:
                failures += 1
                print("FAIL entrada continua no JSON após remove")
        else:
            failures += 1
            print(f"FAIL POST /actions/history/remove -> {r.status_code}")

        # injeta de novo e usa clear-errors
        data2 = _json.loads(hist_path.read_text(encoding="utf-8"))
        data2.append({"file": "AUTO_TEST_ERR2.mkv", "status": "error", "started": "2099-02-01T00:00:00", "completed": None, "details": {}, "stage": 0})
        hist_path.write_text(_json.dumps(data2, ensure_ascii=False, indent=2), encoding="utf-8")
        r = client.post("/actions/history/clear-errors", follow_redirects=False)
        if r.status_code == 303:
            current = _json.loads(hist_path.read_text(encoding="utf-8"))
            err_count = sum(1 for e in current if e.get("status") == "error")
            if err_count == 0:
                print("OK  POST /actions/history/clear-errors (todos limpos)")
            else:
                failures += 1
                print(f"FAIL clear-errors deixou {err_count} erros")
        else:
            failures += 1
            print(f"FAIL POST /actions/history/clear-errors -> {r.status_code}")
    finally:
        # restaura sempre
        hist_path.write_text(hist_backup, encoding="utf-8")

    # 12. toggle de provider — alternar e voltar (sem mexer no .env real)
    initial = client.get("/api/llm").json()["provider"]
    other = "local" if initial == "anthropic" else "anthropic"

    # Backup do .env real para restaurar depois
    from pathlib import Path
    env_file = Path("./.env")
    backup = env_file.read_text(encoding="utf-8") if env_file.exists() else None

    try:
        r = client.post("/actions/llm-provider", data={"provider": other})
        provider_now = client.get("/api/llm").json()["provider"]
        if r.status_code == 200 and provider_now == other:
            print(f"OK  POST /actions/llm-provider ({initial} -> {other})")
        else:
            failures += 1
            print(f"FAIL POST /actions/llm-provider -> {r.status_code} provider={provider_now}")

        # voltar
        client.post("/actions/llm-provider", data={"provider": initial})
        provider_after = client.get("/api/llm").json()["provider"]
        if provider_after == initial:
            print(f"OK  POST /actions/llm-provider (voltou para {initial})")
        else:
            failures += 1
            print(f"FAIL provider não voltou: {provider_after}")
    finally:
        # Restaura .env exatamente como estava
        if backup is not None:
            env_file.write_text(backup, encoding="utf-8")
        elif env_file.exists():
            env_file.unlink()

    print(f"\nResultado: {'TODOS PASSARAM' if failures == 0 else f'{failures} falha(s)'}")
    raise SystemExit(0 if failures == 0 else 1)


if __name__ == "__main__":
    main()
