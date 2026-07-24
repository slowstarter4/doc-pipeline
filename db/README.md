# db

파이프라인이 `DB_TARGET=postgres`일 때 붙는 Postgres 컨테이너. 파이프라인은 이걸
자동 기동하지 않는다 — 여기서 사람이 직접 올렸다 내린다(schemathesis·프론트 npm과
같은 판단: 여러 환경 자동 기동은 깨지기 쉽다).

```bash
cd db
docker compose up -d      # 올리기 (postgres:16, 호스트 포트 55432)
docker compose down       # 내리기 (데이터 유지)
docker compose down -v    # 내리고 데이터까지 삭제
docker compose ps         # 상태
```

- 접속 규약(생성 백엔드가 읽는 표준): `postgresql://doc:doc@localhost:55432/doc`
- 호스트 포트 55432 — 5432·5433은 Windows WinNAT 예약범위(5346-5445)라 bind가 막힌다.
- 이 값(자격증명·포트)은 각 `backend_*.py`의 `_DATABASE_URL` / spring `application.properties`와
  한 쌍이다. 바꾸면 양쪽 다 바꿔야 한다.
