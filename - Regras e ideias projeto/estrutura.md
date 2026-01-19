```
IA_TREVO4FOLHAS/
│
├─ config/
│  └─ paths.py                # caminhos centralizados (único lugar)
│
├─ data/
│  ├─ BD/
│  │  ├─ lotofacil.db         # banco único (tudo persistido)
│  │  └─ connection.py        # conexão única com o sqlite
│  ├─ database/
│  │  └─ db_schema.sql        # schema final (cérebro + treino + auditoria)
│  └─ planilhas/
│     └─ Lotofácil.csv        # CSV oficial (fonte)
│
├─ START/
│  ├─ startBD.py              # cria banco + schema + importa CSV (sem duplicar)
│  └─ update_concursos.py     # atualiza concursos sem duplicar (incremental)
│
├─ training/
│  ├─ trainer_v2.py           # TREINADOR FINAL (N→N+1, checkpoint, gera jogos)
│  ├─ core/
│  │  ├─ brain_interface.py   # contrato FINAL (não mexe mais)
│  │  ├─ base_brain.py        # base com persistência no DB (não mexe mais)
│  │  └─ brain_hub.py         # orquestrador (meta-aprendizado)
│  └─ brains/
│     ├─ statistical/         # cluster estatístico (PASSO 6 pronto)
│     ├─ temporal/            # cluster temporal (PASSO 7)
│     └─ structural/          # cluster estrutural (PASSO 8)
│
├─ install.bat
├─ update_concursos.bat
├─ train_incremental.bat
└─ requirements.txt

```