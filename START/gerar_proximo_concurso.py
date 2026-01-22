diff --git a/START/gerar_proximo_concurso.py b/START/gerar_proximo_concurso.py
index 61c531c33aefb463d695f36dbc07b741cf72a0b3..7d6826e3e0bafa9fb13c87a657f09ce3e51018f7 100644
--- a/START/gerar_proximo_concurso.py
+++ b/START/gerar_proximo_concurso.py
@@ -240,72 +240,81 @@ def insert_pred(
         int(janela),
         int(per_brain),
         int(top_n),
         float(max_sim),
         int(brains_ativos),
         now_str(),
     ]
 
     placeholders = ",".join(["?"] * len(cols))
     sql = f"INSERT OR IGNORE INTO predicoes_proximo ({','.join(cols)}) VALUES ({placeholders})"
 
     cur = conn.cursor()
     cur.execute(sql, values)
     conn.commit()
     return cur.rowcount > 0
 
 
 
 
 # ==========================
 # Registro de cérebros (auto)
 # ==========================
 def register_brains_auto(conn, hub: BrainHub) -> List[str]:
     loaded: List[str] = []
 
+    def _register(brain) -> None:
+        hub.register(brain)
+        loaded.append(getattr(brain, "id", brain.__class__.__name__))
+
     def _try_add(import_path: str, cls_name: str, *args, **kwargs):
-        nonlocal loaded
         try:
             mod = __import__(import_path, fromlist=[cls_name])
             cls = getattr(mod, cls_name)
             b = cls(conn, *args, **kwargs)
-            hub.register(b)
-            loaded.append(getattr(b, "id", f"{import_path}.{cls_name}"))
+            _register(b)
         except Exception:
             pass
 
     # Base (confirmados)
     _try_add("training.brains.statistical.freq_global_brain", "StatFreqGlobalBrain")
     _try_add("training.brains.statistical.freq_recente_brain", "StatFreqRecenteBrain", janela=120)
     _try_add("training.brains.temporal.atraso_brain", "TemporalAtrasoBrain")
 
     # Extras (se existirem)
     _try_add("training.brains.statistical.nucleo_satelites_brain", "StatNucleoSatelitesBrain")
     _try_add("training.brains.exploratory.total_dezenas_auto_brain", "ExplorTotalDezenasAutoBrain")
     _try_add("training.brains.statistical.elite_memory_brain", "StatEliteMemoryBrain")
     _try_add("training.brains.statistical.paridade_faixas_brain", "StatParidadeFaixasBrain")
     _try_add("training.brains.structural.pattern_shape_brain", "StructuralPatternShapeBrain")
+    try:
+        from training.brains.heuristic.heuristic_brains import build_heuristic_brains
+
+        for brain in build_heuristic_brains(conn):
+            _register(brain)
+    except Exception:
+        pass
 
     return loaded
 
 
 # ==========================
 # Scoring final (explicável)
 # ==========================
 def score_freq_recente(jogo: List[int], freq: Dict[int, int]) -> float:
     if not jogo:
         return 0.0
     maxf = max(freq.values()) if freq else 1
     if maxf <= 0:
         return 0.0
     return sum(freq.get(int(d), 0) / maxf for d in jogo) / len(jogo)
 
 
 def score_shape(jogo: List[int], size: int) -> float:
     if not jogo:
         return 0.0
 
     ev = count_even(jogo)
     run = max_consecutive_run(jogo)
 
     if size == 15:
         pares_ok = 1.0 if 6 <= ev <= 9 else 0.6
@@ -342,247 +351,268 @@ def diversify_ranked(items: List[Dict[str, Any]], top_k: int, max_sim: float) ->
     return chosen
 
 
 def get_profile_weights(perfil: str) -> Tuple[float, float, float, float]:
     """
     Retorna pesos: (hub, freq, mem, shape)
     """
     perfil = (perfil or "balanceado").lower().strip()
     if perfil == "conservador":
         # mais “forma” + frequência, menos “memória”
         return (0.50, 0.25, 0.10, 0.15)
     if perfil == "agressivo":
         # confia mais na memória 14/15 e menos em shape
         return (0.55, 0.15, 0.25, 0.05)
     # balanceado
     return (0.55, 0.20, 0.15, 0.10)
 
 
 # ==========================
 # Geração para um tamanho
 # ==========================
 def generate_for_size(
     conn: sqlite3.Connection,
     size: int,
     qtd: int,
+    qtd_strong: int,
     janela: int,
     per_brain: int,
     top_n: int,
     max_sim: float,
     perfil: str,
     salvar_db: bool,
+    exploration_rate: float,
+    max_brain_share: float,
 ) -> Path:
     ultimo_concurso = fetch_max_concurso(conn)
     proximo_concurso = ultimo_concurso + 1
 
     context = build_context(conn, concurso_n=ultimo_concurso, janela_recente=janela)
     freq = context.get("freq_recente", {}) or {}
     memoria_1415 = fetch_memoria_top(conn, min_pontos=14, limit=500)
 
-    hub = BrainHub(conn)
+    hub = BrainHub(conn, exploration_rate=exploration_rate, max_brain_share=max_brain_share)
     loaded = register_brains_auto(conn, hub)
     if not loaded:
         raise RuntimeError("Nenhum cérebro foi carregado. Verifique seus arquivos em training/brains.")
 
     hub.load_all()
 
     candidatos = hub.generate_games(
         context=context,
         size=size,
         per_brain=per_brain,
         top_n=top_n,
     )
     if not candidatos:
         raise RuntimeError("Hub não gerou candidatos.")
 
     w_hub, w_freq, w_mem, w_shape = get_profile_weights(perfil)
 
     ranked: List[Dict[str, Any]] = []
     for c in candidatos:
         jogo = [int(x) for x in c["jogo"]]
         s_hub = float(c.get("score", 0.0))
         s_freq = score_freq_recente(jogo, freq)
         s_mem = score_memoria(jogo, memoria_1415)
         s_shape = score_shape(jogo, size)
 
         score_final = (w_hub * s_hub) + (w_freq * s_freq) + (w_mem * s_mem) + (w_shape * s_shape)
 
         ranked.append({
             "jogo": sorted(jogo),
             "score_final": float(score_final),
             "score_hub": float(s_hub),
             "score_freq": float(s_freq),
             "score_mem": float(s_mem),
             "score_shape": float(s_shape),
             "brain_id": str(c.get("brain_id", "unknown")),
         })
 
     ranked.sort(key=lambda x: x["score_final"], reverse=True)
     final = diversify_ranked(ranked, top_k=qtd, max_sim=max_sim)
+    strongest = ranked[: max(0, int(qtd_strong))]
 
     reports_dir = ROOT / "reports"
     reports_dir.mkdir(parents=True, exist_ok=True)
     out_path = reports_dir / f"proximo_concurso_{proximo_concurso}_jogos_{size}.txt"
 
     lines: List[str] = []
     lines.append("=========================================")
     lines.append("🎯 JOGOS SUGERIDOS — PRÓXIMO CONCURSO")
     lines.append("=========================================")
     lines.append(f"Data/Hora: {now_str()}")
     lines.append(f"Último concurso conhecido: {ultimo_concurso}")
     lines.append(f"Próximo concurso: {proximo_concurso}")
     lines.append(f"Tamanho do jogo: {size}")
     lines.append(f"Cérebros ativos: {len(loaded)}")
     lines.append(f"Perfil: {perfil}")
     lines.append(f"Pesos: hub={w_hub} freq={w_freq} mem={w_mem} shape={w_shape}")
     lines.append(f"Janela (contexto): {janela}")
     lines.append(f"Candidatos por cérebro: {per_brain}")
     lines.append(f"Top_n pós-hub: {top_n}")
     lines.append(f"Diversidade max_sim (Jaccard): {max_sim}")
+    if strongest:
+        lines.append(f"Jogos fortes extras: {len(strongest)}")
     lines.append("=========================================\n")
 
     print(f"\n✅ Jogos finais (priorizados) — size={size} | perfil={perfil}\n")
     for i, item in enumerate(final, 1):
         jogo = item["jogo"]
         print(f"JOGO {i:02d}: {jogo} | score={item['score_final']:.4f} | fonte={item['brain_id']}")
 
         lines.append(f"JOGO {i:02d}: {jogo}")
         lines.append(
             f"  score_final={item['score_final']:.6f} | hub={item['score_hub']:.6f} | "
             f"freq={item['score_freq']:.6f} | mem={item['score_mem']:.6f} | shape={item['score_shape']:.6f} | "
             f"fonte={item['brain_id']}"
         )
         lines.append("")
 
+    if strongest:
+        lines.append("=========================================")
+        lines.append("🔥 JOGOS FORTES (TOP SCORE HUB)")
+        lines.append("=========================================\n")
+        for i, item in enumerate(strongest, 1):
+            jogo = item["jogo"]
+            print(f"FORTE {i:02d}: {jogo} | score={item['score_final']:.4f} | fonte={item['brain_id']}")
+            lines.append(f"FORTE {i:02d}: {jogo}")
+            lines.append(
+                f"  score_final={item['score_final']:.6f} | hub={item['score_hub']:.6f} | "
+                f"freq={item['score_freq']:.6f} | mem={item['score_mem']:.6f} | shape={item['score_shape']:.6f} | "
+                f"fonte={item['brain_id']}"
+            )
+            lines.append("")
+
     lines.append("Observação importante:")
     lines.append("- Loteria é aleatória. Este ranking só prioriza candidatos segundo o aprendizado do sistema.")
     lines.append("- Use com responsabilidade e dentro do seu orçamento.")
     lines.append("")
 
     out_path.write_text("\n".join(lines), encoding="utf-8")
 
     if salvar_db:
         ensure_pred_table(conn)
         inseridos = 0
         for ordem, item in enumerate(final, 1):
             ok = insert_pred(
                 conn=conn,
                 concurso_previsto=proximo_concurso,
                 tamanho=size,
                 ordem=ordem,
                 dezenas=item["jogo"],
                 score_final=item["score_final"],
                 score_hub=item["score_hub"],
                 score_freq=item["score_freq"],
                 score_mem=item["score_mem"],
                 score_shape=item["score_shape"],
                 perfil=perfil,
                 janela=janela,
                 per_brain=per_brain,
                 top_n=top_n,
                 max_sim=max_sim,
                 brains_ativos=len(loaded),
             )
             if ok:
                 inseridos += 1
         log(f"💾 Predições salvas em DB: {inseridos}/{len(final)} (tabela predicoes_proximo)")
 
     log(f"📄 Relatório salvo em: {out_path}")
     return out_path
 
 
 # ==========================
 # MAIN
 # ==========================
 def main() -> None:
     parser = argparse.ArgumentParser(description="Gerar jogos para o próximo concurso usando BrainHub + memória + contexto.")
-    parser.add_argument("--size", type=int, default=15, help="Tamanho do jogo (15 ou 18).")
-    parser.add_argument("--qtd", type=int, default=10, help="Quantidade de jogos finais.")
+    parser.add_argument("--size", type=int, default=15, help="Tamanho do jogo principal (15, 16, 18 ou 19).")
+    parser.add_argument("--qtd", type=int, default=10, help="Quantidade de jogos finais do tamanho principal.")
+    parser.add_argument("--qtd-strong", type=int, default=1, help="Quantidade de jogos fortes extras (top score).")
+    parser.add_argument("--second-size", type=int, default=None, help="Segundo tamanho opcional (15, 16, 18 ou 19).")
+    parser.add_argument("--second-qtd", type=int, default=None, help="Quantidade de jogos do segundo tamanho.")
     parser.add_argument("--janela", type=int, default=300, help="Janela de histórico para contexto.")
     parser.add_argument("--per-brain", type=int, default=120, help="Candidatos por cérebro.")
     parser.add_argument("--top-n", type=int, default=250, help="Top candidatos após BrainHub (antes do re-ranking).")
     parser.add_argument("--max-sim", type=float, default=0.78, help="Diversidade (Jaccard máximo entre jogos finais).")
+    parser.add_argument("--exploration-rate", type=float, default=0.10, help="Taxa de exploração do BrainHub.")
+    parser.add_argument("--max-brain-share", type=float, default=0.4, help="Limite de participação por cérebro no Top N.")
     parser.add_argument("--perfil", type=str, default="balanceado", choices=["conservador", "balanceado", "agressivo"])
     parser.add_argument("--salvar-db", action="store_true", help="Salvar jogos gerados na tabela predicoes_proximo.")
-    parser.add_argument("--both", action="store_true", help="Gerar 15 e 18 no mesmo comando (usa --qtd15 e --qtd18).")
-    parser.add_argument("--qtd15", type=int, default=10, help="Qtd jogos para size=15 (quando --both).")
-    parser.add_argument("--qtd18", type=int, default=7, help="Qtd jogos para size=18 (quando --both).")
     parser.add_argument("--seed", type=int, default=None, help="Seed para reprodutibilidade (opcional).")
     args = parser.parse_args()
 
     if args.seed is not None:
         random.seed(int(args.seed))
 
     db_path = Path(DB_PATH)
     if not db_path.exists():
         log(f"❌ DB não encontrado em: {db_path}")
         log("Rode primeiro: python START\\startBD.py")
         return
 
     conn = get_conn()
     try:
         if not safe_table_exists(conn, "concursos"):
             log("❌ Tabela 'concursos' não existe. Rode START/startBD.py.")
             return
 
         ultimo_concurso = fetch_max_concurso(conn)
         if ultimo_concurso < 1:
             log("❌ Sem concursos no banco. Importe o CSV e rode START/startBD.py.")
             return
 
         log("=========================================")
         log("🎯 GERADOR — PRÓXIMO CONCURSO (BrainHub)")
         log("=========================================")
         log(f"📌 DB: {Path(DB_PATH)}")
         log(f"📌 Último concurso no DB : {ultimo_concurso}")
         log(f"📌 Próximo concurso      : {ultimo_concurso + 1}")
         log("=========================================")
 
-        if args.both:
-            generate_for_size(
-                conn=conn,
-                size=15,
-                qtd=max(1, int(args.qtd15)),
-                janela=max(50, int(args.janela)),
-                per_brain=max(10, int(args.per_brain)),
-                top_n=max(50, int(args.top_n)),
-                max_sim=float(args.max_sim),
-                perfil=str(args.perfil),
-                salvar_db=bool(args.salvar_db),
-            )
-            generate_for_size(
-                conn=conn,
-                size=18,
-                qtd=max(1, int(args.qtd18)),
-                janela=max(50, int(args.janela)),
-                per_brain=max(10, int(args.per_brain)),
-                top_n=max(50, int(args.top_n)),
-                max_sim=float(args.max_sim),
-                perfil=str(args.perfil),
-                salvar_db=bool(args.salvar_db),
-            )
-        else:
-            size = int(args.size)
-            if size not in (15, 18):
-                size = 15
+        size = int(args.size)
+        if size not in (15, 16, 18, 19):
+            size = 15
+
+        generate_for_size(
+            conn=conn,
+            size=size,
+            qtd=max(1, int(args.qtd)),
+            qtd_strong=max(0, int(args.qtd_strong)),
+            janela=max(50, int(args.janela)),
+            per_brain=max(10, int(args.per_brain)),
+            top_n=max(50, int(args.top_n)),
+            max_sim=float(args.max_sim),
+            perfil=str(args.perfil),
+            salvar_db=bool(args.salvar_db),
+            exploration_rate=float(args.exploration_rate),
+            max_brain_share=float(args.max_brain_share),
+        )
 
+        if args.second_size is not None and args.second_qtd is not None:
+            second_size = int(args.second_size)
+            if second_size not in (15, 16, 18, 19):
+                second_size = 18
             generate_for_size(
                 conn=conn,
-                size=size,
-                qtd=max(1, int(args.qtd)),
+                size=second_size,
+                qtd=max(1, int(args.second_qtd)),
+                qtd_strong=0,
                 janela=max(50, int(args.janela)),
                 per_brain=max(10, int(args.per_brain)),
                 top_n=max(50, int(args.top_n)),
                 max_sim=float(args.max_sim),
                 perfil=str(args.perfil),
                 salvar_db=bool(args.salvar_db),
+                exploration_rate=float(args.exploration_rate),
+                max_brain_share=float(args.max_brain_share),
             )
 
     finally:
         try:
             conn.close()
         except Exception:
             pass
 
 
 if __name__ == "__main__":
     main()
