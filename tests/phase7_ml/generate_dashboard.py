"""
ML 평가 대시보드 생성 (generate_dashboard.py)
==============================================
역할:
  5축 평가 결과 CSV + run_meta.json을 읽어
  논문 발표용 시각화 대시보드 HTML 파일을 생성한다.

설계 원칙 (교수님 피드백 반영):
  1. 차트 스타일: 꺾은선(line) 위주 — 논문 정형 패턴
  2. 지표 추가: AUC, MAE, MSE 포함
  3. 줄임말 풀어쓰기: IF→Isolation Forest 등
  4. 표 하이라이트: 최고/최저값 명확 강조

입력: tests/phase7_ml/results/{run_id}/ 아래 CSV 5개 + run_meta.json
출력: 같은 디렉토리에 dashboard.html 생성

위치: tests/phase7_ml/generate_dashboard.py

실행 방법:
  python tests/phase7_ml/generate_dashboard.py
  python tests/phase7_ml/generate_dashboard.py --run run_20260513_143022
  python tests/phase7_ml/generate_dashboard.py --compare run_20260513_143022 run_20260515_221700
"""

import sys
import os
import json
import argparse
import pandas as pd
import numpy as np
from pathlib import Path


# ---------------------------------------------------------------------------
# 데이터 로딩
# ---------------------------------------------------------------------------
def load_run_data(run_dir):
    run_dir = Path(run_dir)
    data = {}
    data["axis1"] = pd.read_csv(run_dir / "axis1_esr.csv", encoding="utf-8-sig")
    data["axis2"] = pd.read_csv(run_dir / "axis2_separation.csv", encoding="utf-8-sig")
    data["axis3"] = pd.read_csv(run_dir / "axis3_auc.csv", encoding="utf-8-sig")
    data["axis4"] = pd.read_csv(run_dir / "axis4_sensitivity.csv", encoding="utf-8-sig")
    data["axis5"] = pd.read_csv(run_dir / "axis5_consensus.csv", encoding="utf-8-sig")
    meta_path = run_dir / "run_meta.json"
    if meta_path.exists():
        with open(meta_path, "r", encoding="utf-8") as f:
            data["meta"] = json.load(f)
    else:
        data["meta"] = {"run_id": run_dir.name, "memo": "", "timestamp": "unknown"}
    roc_path = run_dir / "axis3_roc_curves.json"
    if roc_path.exists():
        with open(roc_path, "r", encoding="utf-8") as f:
            data["roc_curves"] = json.load(f)
    else:
        data["roc_curves"] = {}
    return data


def df_to_js_array(df, columns, null_val="null"):
    rows = []
    for _, row in df.iterrows():
        obj_parts = []
        for col in columns:
            val = row[col]
            if isinstance(val, str):
                obj_parts.append(f'{col}:"{val}"')
            elif pd.isna(val):
                obj_parts.append(f"{col}:{null_val}")
            elif isinstance(val, bool) or isinstance(val, np.bool_):
                obj_parts.append(f"{col}:{'true' if val else 'false'}")
            elif isinstance(val, (int, np.integer)):
                obj_parts.append(f"{col}:{val}")
            else:
                obj_parts.append(f"{col}:{val}")
        rows.append("{" + ",".join(obj_parts) + "}")
    return "[" + ",\n  ".join(rows) + "]"


# ---------------------------------------------------------------------------
# 비교 배너
# ---------------------------------------------------------------------------
def build_compare_banner(meta_current, meta_previous):
    if not meta_previous:
        return ""
    sc = meta_current.get("summary", {})
    sp = meta_previous.get("summary", {})
    def delta_html(key, fmt=".4f", higher_is_better=True):
        vc, vp = sc.get(key), sp.get(key)
        if vc is None or vp is None: return '<span style="color:var(--text-muted)">—</span>'
        d = vc - vp
        if abs(d) < 0.0001: return '<span style="color:var(--text-muted)">±0</span>'
        color = "var(--grade-good)" if (d > 0) == higher_is_better else "var(--grade-weak)"
        sign = "+" if d > 0 else ""
        return f'<span style="color:{color};font-weight:700">{sign}{d:{fmt}}</span>'
    rows = [("Weighted ESR",delta_html("weighted_esr")),("Avg Separation Ratio (IF)",delta_html("avg_sr_if",".3f")),
            ("AUC (Ensemble)",delta_html("avg_auc_ensemble")),("Contamination SR",delta_html("avg_contam_sr")),
            ("Cross-Track Agreement",delta_html("avg_cta"))]
    cells = "".join(f'<div style="text-align:center"><div style="font-size:11px;color:var(--text-muted)">{n}</div><div style="font-size:18px;margin-top:4px">{v}</div></div>' for n, v in rows)
    return f'<div style="background:var(--bg-card);border:1px solid var(--border);border-radius:12px;padding:20px;margin-bottom:32px"><div style="font-size:13px;color:var(--text-muted);margin-bottom:12px;font-family:\'JetBrains Mono\',monospace">vs {meta_previous.get("run_id","?")} — {meta_previous.get("memo","")}</div><div style="display:grid;grid-template-columns:repeat(5,1fr);gap:16px">{cells}</div></div>'


# ---------------------------------------------------------------------------
# HTML 생성
# ---------------------------------------------------------------------------
def generate_html(data, compare_data=None):
    meta = data["meta"]
    run_id = meta.get("run_id", "unknown")
    memo = meta.get("memo", "")
    timestamp = meta.get("timestamp", "")
    n_features = meta.get("features", {}).get("n_features", "?")
    feature_list = meta.get("features", {}).get("feature_list", [])

    axis1_js = df_to_js_array(data["axis1"], ["commodity_id","segment","n_shocks","esr_if","esr_lof","esr_svm","esr_ml"])
    axis2_js = df_to_js_array(data["axis2"], ["commodity_id","segment","sr_if","sr_lof","sr_svm"])
    axis3_js = df_to_js_array(data["axis3"], ["commodity_id","segment","auc_if","auc_lof","auc_svm","auc_ensemble"])
    axis4_js = df_to_js_array(data["axis4"], ["commodity_id","segment","n_base","avg_contam_sr","avg_k_sr"])
    axis5_js = df_to_js_array(data["axis5"], ["commodity_id","segment","cta","asc","p_stat","p_ml","esr_stat","esr_ml","n_shocks","hypothesis_holds"])

    # ROC curve 데이터 → JS 객체 리터럴
    roc_curves_js = json.dumps(data.get("roc_curves", {}))

    compare_banner = build_compare_banner(meta, compare_data["meta"]) if compare_data else ""
    feature_badge = f"{n_features}: {', '.join(feature_list)}" if feature_list else f"{n_features}"

    html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Phase 7-ML 5-Axis Reliability Report — {run_id}</title>
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@300;400;500;700;900&family=JetBrains+Mono:wght@400;500;700&display=swap" rel="stylesheet">
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
<style>
:root {{ --bg-primary:#0a0e17; --bg-card:#111827; --border:#1e293b; --text-primary:#e2e8f0; --text-secondary:#94a3b8; --text-muted:#64748b; --accent-blue:#3b82f6; --accent-cyan:#06b6d4; --accent-emerald:#10b981; --accent-amber:#f59e0b; --accent-rose:#f43f5e; --accent-violet:#8b5cf6; --grade-good:#10b981; --grade-moderate:#f59e0b; --grade-weak:#f43f5e; }}
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ font-family:'Noto Sans KR',sans-serif; background:var(--bg-primary); color:var(--text-primary); min-height:100vh; line-height:1.6; }}
.container {{ max-width:1400px; margin:0 auto; padding:40px 32px; }}
.header {{ text-align:center; margin-bottom:48px; }}
.header::after {{ content:''; display:block; width:120px; height:2px; background:linear-gradient(90deg,var(--accent-blue),var(--accent-cyan)); margin:24px auto 0; }}
.header h1 {{ font-size:26px; font-weight:900; background:linear-gradient(135deg,#e2e8f0,#94a3b8); -webkit-background-clip:text; -webkit-text-fill-color:transparent; }}
.header .subtitle {{ font-size:13px; color:var(--text-muted); margin-top:8px; font-family:'JetBrains Mono',monospace; }}
.header .run-info {{ font-size:12px; color:var(--text-muted); margin-top:4px; font-family:'JetBrains Mono',monospace; }}
.header .memo-badge {{ display:inline-block; background:rgba(59,130,246,0.12); color:var(--accent-blue); padding:3px 12px; border-radius:20px; font-size:12px; margin-top:8px; }}
.summary-row {{ display:grid; grid-template-columns:repeat(5,1fr); gap:16px; margin-bottom:40px; }}
.summary-card {{ background:var(--bg-card); border:1px solid var(--border); border-radius:12px; padding:20px; text-align:center; position:relative; overflow:hidden; }}
.summary-card::before {{ content:''; position:absolute; top:0; left:0; right:0; height:3px; }}
.summary-card:nth-child(1)::before {{ background:var(--accent-blue); }}
.summary-card:nth-child(2)::before {{ background:var(--accent-cyan); }}
.summary-card:nth-child(3)::before {{ background:var(--accent-violet); }}
.summary-card:nth-child(4)::before {{ background:var(--accent-emerald); }}
.summary-card:nth-child(5)::before {{ background:var(--accent-amber); }}
.summary-card .axis-label {{ font-size:11px; font-family:'JetBrains Mono',monospace; color:var(--text-muted); text-transform:uppercase; letter-spacing:1px; margin-bottom:4px; }}
.summary-card .axis-name {{ font-size:12px; font-weight:500; color:var(--text-secondary); margin-bottom:12px; }}
.summary-card .value {{ font-size:30px; font-weight:900; font-family:'JetBrains Mono',monospace; margin-bottom:4px; }}
.summary-card .grade {{ font-size:12px; font-weight:700; padding:3px 10px; border-radius:20px; display:inline-block; }}
.grade-good {{ background:rgba(16,185,129,0.15); color:var(--grade-good); }}
.grade-moderate {{ background:rgba(245,158,11,0.15); color:var(--grade-moderate); }}
.grade-weak {{ background:rgba(244,63,94,0.15); color:var(--grade-weak); }}
.section {{ margin-bottom:48px; }}
.section-header {{ display:flex; align-items:center; gap:12px; margin-bottom:20px; padding-bottom:12px; border-bottom:1px solid var(--border); }}
.section-number {{ font-family:'JetBrains Mono',monospace; font-size:12px; font-weight:700; color:var(--accent-blue); background:rgba(59,130,246,0.1); padding:4px 10px; border-radius:6px; }}
.section-title {{ font-size:17px; font-weight:700; }}
.section-desc {{ font-size:12px; color:var(--text-muted); margin-left:auto; }}
.chart-grid {{ display:grid; grid-template-columns:1fr 1fr; gap:20px; }}
.chart-card {{ background:var(--bg-card); border:1px solid var(--border); border-radius:12px; padding:24px; }}
.chart-card h3 {{ font-size:13px; font-weight:500; color:var(--text-secondary); margin-bottom:16px; }}
.chart-container.wide {{ position:relative; width:100%; height:360px; }}
.radar-wrapper {{ display:grid; grid-template-columns:1fr 1fr; gap:20px; }}
.radar-card {{ background:var(--bg-card); border:1px solid var(--border); border-radius:12px; padding:24px; display:flex; flex-direction:column; align-items:center; }}
.radar-card h3 {{ font-size:13px; font-weight:500; color:var(--text-secondary); margin-bottom:16px; }}
table.eval {{ width:100%; border-collapse:collapse; font-size:11px; font-family:'JetBrains Mono',monospace; }}
table.eval th {{ padding:8px 5px; font-weight:500; color:var(--text-muted); text-align:center; border-bottom:1px solid var(--border); font-size:10px; }}
table.eval th:first-child {{ text-align:left; min-width:85px; }}
table.eval td {{ padding:5px; text-align:center; border-bottom:1px solid rgba(30,41,59,0.5); }}
table.eval td:first-child {{ text-align:left; font-weight:500; color:var(--text-secondary); }}
.hl {{ display:inline-block; padding:1px 5px; border-radius:3px; font-weight:600; min-width:44px; font-size:11px; }}
.hl-best {{ background:rgba(16,185,129,0.22); color:#6ee7b7; }}
.hl-worst {{ background:rgba(244,63,94,0.18); color:#fda4af; }}
.hl-na {{ background:rgba(100,116,139,0.15); color:var(--text-muted); }}
.hyp-true {{ background:rgba(16,185,129,0.2); color:var(--grade-good); padding:2px 8px; border-radius:4px; font-weight:700; font-size:11px; }}
.hyp-false {{ background:rgba(244,63,94,0.15); color:var(--grade-weak); padding:2px 8px; border-radius:4px; font-weight:700; font-size:11px; }}
.hyp-na {{ background:rgba(100,116,139,0.15); color:var(--text-muted); padding:2px 8px; border-radius:4px; font-weight:700; font-size:11px; }}
.footer {{ text-align:center; padding:32px 0; border-top:1px solid var(--border); color:var(--text-muted); font-size:12px; font-family:'JetBrains Mono',monospace; }}
@media print {{ body {{ background:#fff; color:#1a1a1a; }} .summary-card,.chart-card,.radar-card {{ border-color:#ddd; background:#fafafa; }} .header h1 {{ -webkit-text-fill-color:#1a1a1a; }} }}
@media (max-width:1024px) {{ .summary-row {{ grid-template-columns:repeat(3,1fr); }} .chart-grid,.radar-wrapper {{ grid-template-columns:1fr; }} }}
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <h1>Phase 7-ML · 5-Axis Reliability Evaluation Report</h1>
    <div class="subtitle">Unsupervised Anomaly Detection — 10 Commodities × 2 Segments (A, B) = 20 Units</div>
    <div class="run-info">{run_id} · {timestamp} · Features: {feature_badge}</div>
    {"<div class='memo-badge'>" + memo + "</div>" if memo and memo != "메모 없음" else ""}
  </div>
  {compare_banner}
  <div class="summary-row" id="summaryCards"></div>

  <div class="section"><div class="section-header"><span class="section-number">AXIS 1</span><span class="section-title">External Shock Recall (ESR)</span><span class="section-desc">≥1 detection within shock window → recovered</span></div>
    <div class="chart-grid">
      <div class="chart-card"><h3>Ensemble External Shock Recall by Commodity × Segment</h3><div class="chart-container wide"><canvas id="esr_line"></canvas></div></div>
      <div class="chart-card"><h3>Model-wise External Shock Recall</h3><div class="chart-container wide"><canvas id="esr_model"></canvas></div></div>
    </div></div>

  <div class="section"><div class="section-header"><span class="section-number">AXIS 2</span><span class="section-title">Anomaly Score Separation Ratio</span><span class="section-desc">SR &gt; 2.0 Good · 1.0~2.0 Moderate · &lt;1.0 Weak</span></div>
    <div class="chart-grid">
      <div class="chart-card"><h3>Separation Ratio by Model</h3><div class="chart-container wide"><canvas id="sr_line"></canvas></div></div>
      <div class="chart-card"><h3>Separation Ratio Detail</h3><div id="sr_table"></div></div>
    </div></div>

  <div class="section"><div class="section-header"><span class="section-number">AXIS 3</span><span class="section-title">Statistical–ML Consistency (AUC / MAE / MSE)</span><span class="section-desc">Ideal AUC: 0.70~0.90</span></div>
    <div class="chart-grid">
      <div class="chart-card"><h3>ROC AUC by Model (per Unit)</h3><div class="chart-container wide"><canvas id="auc_line"></canvas></div></div>
      <div class="chart-card"><h3>ROC Curve <select id="roc_select" style="background:var(--bg-primary);color:var(--text-primary);border:1px solid var(--border);border-radius:4px;padding:2px 6px;font-size:11px;font-family:'JetBrains Mono',monospace;margin-left:8px;"></select></h3><div class="chart-container wide"><canvas id="roc_curve"></canvas></div></div>
    </div>
    <div style="margin-top:20px">
      <div class="chart-card"><h3>AUC / MAE / MSE Detail</h3><div id="auc_table"></div></div>
    </div></div>

  <div class="section"><div class="section-header"><span class="section-number">AXIS 4</span><span class="section-title">Hyperparameter Sensitivity (Stability Ratio)</span><span class="section-desc">SR ≥ 0.80 Robust · 0.60~0.80 Moderate</span></div>
    <div class="chart-grid">
      <div class="chart-card"><h3>Stability Ratio: Contamination vs LOF k-value</h3><div class="chart-container wide"><canvas id="sens_line"></canvas></div></div>
      <div class="chart-card"><h3>Sensitivity Detail</h3><div id="sens_table"></div></div>
    </div></div>

  <div class="section"><div class="section-header"><span class="section-number">AXIS 5</span><span class="section-title">Consensus (CTA + ASC + P_stat + P_ml)</span><span class="section-desc">Hypothesis: ASC &gt; max(P_stat, P_ml)</span></div>
    <div class="chart-grid">
      <div class="chart-card"><h3>Consensus Indicators by Commodity × Segment</h3><div class="chart-container wide"><canvas id="cons_line"></canvas></div></div>
      <div class="chart-card"><h3>Hypothesis Verification</h3><div id="hyp_table"></div></div>
    </div></div>

  <div class="section"><div class="section-header"><span class="section-number">SUMMARY</span><span class="section-title">5-Axis Normalized Radar</span></div>
    <div class="radar-wrapper">
      <div class="radar-card"><h3>Normalized Scores (0~1)</h3><div style="width:340px;height:340px;"><canvas id="radar_all"></canvas></div></div>
      <div class="radar-card"><h3>Axis-wise Verdict</h3><div id="verdict_table" style="width:100%;"></div></div>
    </div></div>

  <div class="footer">Phase 7-ML Reliability Evaluation · Sunmoon University Capstone Design 11-1 · {run_id}</div>
</div>

<script>
const axis1={axis1_js};
const axis2={axis2_js};
const axis3={axis3_js};
const axis4={axis4_js};
const axis5={axis5_js};

const labels20=axis1.map(d=>d.commodity_id+' '+d.segment);
const avg=arr=>{{const v=arr.filter(x=>x!==null&&!isNaN(x));return v.length?v.reduce((a,b)=>a+b,0)/v.length:NaN;}};
Chart.defaults.color='#94a3b8';Chart.defaults.borderColor='rgba(30,41,59,0.6)';
Chart.defaults.font.family="'JetBrains Mono','Noto Sans KR',sans-serif";Chart.defaults.font.size=11;

const C={{if:'#3b82f6',lof:'#06b6d4',svm:'#8b5cf6',ens:'#10b981',contam:'#f59e0b',k:'#06b6d4',cta:'#3b82f6',asc:'#10b981',ps:'#f59e0b',pm:'#8b5cf6'}};
function lds(label,data,color,dash){{return{{label,data,borderColor:color,backgroundColor:color+'33',tension:0.3,pointRadius:3,pointHoverRadius:6,borderWidth:2,fill:false,borderDash:dash||[]}};}}
function bds(label,data,color){{return{{label,data,backgroundColor:color+'99',borderColor:color,borderWidth:1,borderRadius:3,barPercentage:0.8}};}}

function gradeText(v,t,l){{if(v===null||isNaN(v))return['—','grade-moderate'];if(v>=t[0])return[l[0],'grade-good'];if(v>=t[1])return[l[1],'grade-moderate'];return[l[2],'grade-weak'];}}

function hlCell(val,all,dec,hb=true){{
  if(val===null||isNaN(val))return'<span class="hl hl-na">—</span>';
  const vl=all.filter(v=>v!==null&&!isNaN(v));if(!vl.length)return'<span class="hl">'+val.toFixed(dec)+'</span>';
  const best=hb?Math.max(...vl):Math.min(...vl);const worst=hb?Math.min(...vl):Math.max(...vl);
  let cls='';if(Math.abs(val-best)<1e-8)cls='hl-best';else if(Math.abs(val-worst)<1e-8)cls='hl-worst';
  return`<span class="hl ${{cls}}">${{val.toFixed(dec)}}</span>`;
}}

// Summary
const esrV=axis1.filter(d=>d.esr_ml!==null);
const tS=axis1.filter(d=>d.n_shocks>0).reduce((s,d)=>s+d.n_shocks,0);
const wESR=tS>0?esrV.reduce((s,d)=>s+d.esr_ml*d.n_shocks,0)/tS:NaN;
const aSR=avg([...axis2.map(d=>d.sr_if),...axis2.map(d=>d.sr_lof),...axis2.map(d=>d.sr_svm)]);
const aAUC=avg(axis3.map(d=>d.auc_ensemble));
const aCS=avg(axis4.map(d=>d.avg_contam_sr)),aKS=avg(axis4.map(d=>d.avg_k_sr)),aSens=(aCS+aKS)/2;
const aCTA=avg(axis5.map(d=>d.cta));

const sd=[
  {{a:'AXIS 1',n:'External Shock Recall',v:wESR,f:v=>v.toFixed(2),t:[0.70,0.50],l:['Good','Moderate','Weak']}},
  {{a:'AXIS 2',n:'Separation Ratio',v:aSR,f:v=>v.toFixed(2),t:[2.0,1.0],l:['Good','Moderate','Weak']}},
  {{a:'AXIS 3',n:'AUC (Ensemble)',v:aAUC,f:v=>v.toFixed(3),t:[0.70,0.50],l:['Ideal','Independent','Inverse']}},
  {{a:'AXIS 4',n:'Stability Ratio',v:aSens,f:v=>v.toFixed(2),t:[0.80,0.60],l:['Robust','Moderate','Fragile']}},
  {{a:'AXIS 5',n:'Cross-Track Agreement',v:aCTA,f:v=>v.toFixed(3),t:[0.30,0.15],l:['Good','Low','Very Low']}},
];
const sc=document.getElementById('summaryCards');
sd.forEach(d=>{{const[lb,cl]=gradeText(d.v,d.t,d.l);const co=cl==='grade-good'?'var(--grade-good)':cl==='grade-moderate'?'var(--grade-moderate)':'var(--grade-weak)';sc.innerHTML+=`<div class="summary-card"><div class="axis-label">${{d.a}}</div><div class="axis-name">${{d.n}}</div><div class="value" style="color:${{co}}">${{d.f(d.v)}}</div><span class="grade ${{cl}}">${{lb}}</span></div>`;}});

// Axis 1 (bar — independent unit comparison)
const eL=esrV.map(d=>d.commodity_id+' '+d.segment);
new Chart(document.getElementById('esr_line'),{{type:'bar',data:{{labels:eL,datasets:[bds('Ensemble External Shock Recall',esrV.map(d=>d.esr_ml),C.ens)]}},options:{{responsive:true,maintainAspectRatio:false,plugins:{{legend:{{display:false}}}},scales:{{x:{{ticks:{{font:{{size:9}},maxRotation:45}}}},y:{{min:0,max:1.1,title:{{display:true,text:'External Shock Recall'}}}}}}}}}});
new Chart(document.getElementById('esr_model'),{{type:'bar',data:{{labels:eL,datasets:[bds('Isolation Forest',esrV.map(d=>d.esr_if),C.if),bds('Local Outlier Factor',esrV.map(d=>d.esr_lof),C.lof),bds('One-Class SVM',esrV.map(d=>d.esr_svm),C.svm)]}},options:{{responsive:true,maintainAspectRatio:false,plugins:{{legend:{{position:'top',labels:{{boxWidth:12}}}}}},scales:{{x:{{ticks:{{font:{{size:9}},maxRotation:45}}}},y:{{min:0,max:1.1,title:{{display:true,text:'External Shock Recall'}}}}}}}}}});

// Axis 2 (bar — independent unit comparison)
new Chart(document.getElementById('sr_line'),{{type:'bar',data:{{labels:labels20,datasets:[bds('Isolation Forest',axis2.map(d=>d.sr_if),C.if),bds('Local Outlier Factor',axis2.map(d=>d.sr_lof),C.lof),bds('One-Class SVM',axis2.map(d=>d.sr_svm),C.svm)]}},options:{{responsive:true,maintainAspectRatio:false,plugins:{{legend:{{position:'top',labels:{{boxWidth:12}}}}}},scales:{{x:{{ticks:{{font:{{size:8}},maxRotation:60}}}},y:{{min:0,title:{{display:true,text:'Separation Ratio'}}}}}}}}}});

let srH='<table class="eval"><thead><tr><th>Commodity</th><th>Isolation Forest</th><th>Local Outlier Factor</th><th>One-Class SVM</th><th>Average</th></tr></thead><tbody>';
const allSR=axis2.flatMap(d=>[d.sr_if,d.sr_lof,d.sr_svm]);
axis2.forEach(d=>{{const a=(d.sr_if+d.sr_lof+d.sr_svm)/3;srH+=`<tr><td>${{d.commodity_id}} ${{d.segment}}</td><td>${{hlCell(d.sr_if,allSR,2)}}</td><td>${{hlCell(d.sr_lof,allSR,2)}}</td><td>${{hlCell(d.sr_svm,allSR,2)}}</td><td>${{hlCell(a,allSR,2)}}</td></tr>`;}});
srH+='</tbody></table>';document.getElementById('sr_table').innerHTML=srH;

// Axis 3 (bar for AUC per unit, scatter for ROC curve)
new Chart(document.getElementById('auc_line'),{{type:'bar',data:{{labels:labels20,datasets:[bds('Isolation Forest',axis3.map(d=>d.auc_if),C.if),bds('Local Outlier Factor',axis3.map(d=>d.auc_lof),C.lof),bds('One-Class SVM',axis3.map(d=>d.auc_svm),C.svm),bds('Ensemble',axis3.map(d=>d.auc_ensemble),C.ens)]}},options:{{responsive:true,maintainAspectRatio:false,plugins:{{legend:{{position:'top',labels:{{boxWidth:12}}}}}},scales:{{x:{{ticks:{{font:{{size:8}},maxRotation:60}}}},y:{{min:0.3,max:1.0,title:{{display:true,text:'ROC AUC'}}}}}}}}}});

let aH='<table class="eval"><thead><tr><th>Commodity</th><th>AUC (Isol. Forest)</th><th>AUC (LOF)</th><th>AUC (OC-SVM)</th><th>AUC (Ensemble)</th><th>MAE*</th><th>MSE*</th></tr></thead><tbody>';
const allAUCe=axis3.map(d=>d.auc_ensemble),allMAE=axis3.map(d=>+(1-d.auc_ensemble).toFixed(4)),allMSE=axis3.map(d=>+((1-d.auc_ensemble)**2).toFixed(6));
axis3.forEach(d=>{{const mae=+(1-d.auc_ensemble).toFixed(4);const mse=+((1-d.auc_ensemble)**2).toFixed(6);aH+=`<tr><td>${{d.commodity_id}} ${{d.segment}}</td><td>${{hlCell(d.auc_if,axis3.map(x=>x.auc_if),4)}}</td><td>${{hlCell(d.auc_lof,axis3.map(x=>x.auc_lof),4)}}</td><td>${{hlCell(d.auc_svm,axis3.map(x=>x.auc_svm),4)}}</td><td>${{hlCell(d.auc_ensemble,allAUCe,4)}}</td><td>${{hlCell(mae,allMAE,4,false)}}</td><td>${{hlCell(mse,allMSE,4,false)}}</td></tr>`;}});
aH+='</tbody></table><div style="font-size:10px;color:var(--text-muted);margin-top:8px">* MAE ≈ 1−AUC, MSE ≈ (1−AUC)² — pseudo-label (stat_detected) proxy. Lower is better.</div>';
document.getElementById('auc_table').innerHTML=aH;

// ROC Curve (interactive — dropdown selector)
const rocData={roc_curves_js};
const rocKeys=Object.keys(rocData).filter(k=>rocData[k].auc_if&&rocData[k].auc_if[0].length>0);
const rocSel=document.getElementById('roc_select');
rocKeys.forEach((k,i)=>{{const o=document.createElement('option');o.value=k;o.textContent=k.replace('_',' ');if(i===0)o.selected=true;rocSel.appendChild(o);}});
if(rocKeys.length===0){{const o=document.createElement('option');o.textContent='No ROC data';rocSel.appendChild(o);}}

let rocChart=null;
function drawROC(key){{
  const rd=rocData[key];if(!rd)return;
  const datasets=[];
  const modelMap=[['auc_if','Isolation Forest',C.if,[]],['auc_lof','Local Outlier Factor',C.lof,[]],['auc_svm','One-Class SVM',C.svm,[5,5]],['auc_ensemble','Ensemble',C.ens,[]]];
  modelMap.forEach(([mk,label,color,dash])=>{{
    const curve=rd[mk];if(!curve||!curve[0]||curve[0].length===0)return;
    const fpr=curve[0],tpr=curve[1];
    const pts=fpr.map((x,i)=>({{x,y:tpr[i]}}));
    datasets.push({{label,data:pts,borderColor:color,backgroundColor:color+'22',tension:0,pointRadius:0,borderWidth:2,fill:false,borderDash:dash,showLine:true}});
  }});
  // diagonal (random classifier)
  datasets.push({{label:'Random (AUC=0.5)',data:[{{x:0,y:0}},{{x:1,y:1}}],borderColor:'rgba(100,116,139,0.4)',borderWidth:1,borderDash:[4,4],pointRadius:0,fill:false,showLine:true}});
  if(rocChart)rocChart.destroy();
  rocChart=new Chart(document.getElementById('roc_curve'),{{type:'scatter',data:{{datasets}},options:{{responsive:true,maintainAspectRatio:false,plugins:{{legend:{{position:'top',labels:{{boxWidth:12,font:{{size:10}}}}}}}},scales:{{x:{{type:'linear',min:0,max:1,title:{{display:true,text:'False Positive Rate (FPR)'}}}},y:{{type:'linear',min:0,max:1,title:{{display:true,text:'True Positive Rate (TPR)'}}}}}}}}}});
}}
if(rocKeys.length>0)drawROC(rocKeys[0]);
rocSel.addEventListener('change',()=>drawROC(rocSel.value));

// Axis 4
new Chart(document.getElementById('sens_line'),{{type:'line',data:{{labels:labels20,datasets:[lds('Contamination Stability Ratio',axis4.map(d=>d.avg_contam_sr),C.contam),lds('LOF k-value Stability Ratio',axis4.map(d=>d.avg_k_sr),C.k)]}},options:{{responsive:true,maintainAspectRatio:false,plugins:{{legend:{{position:'top',labels:{{boxWidth:12}}}}}},scales:{{x:{{ticks:{{font:{{size:8}},maxRotation:60}}}},y:{{min:0.4,max:1.05,title:{{display:true,text:'Stability Ratio'}}}}}}}}}});

let sH='<table class="eval"><thead><tr><th>Commodity</th><th>Base Detections</th><th>Contamination SR</th><th>LOF k SR</th></tr></thead><tbody>';
const allCS=axis4.map(d=>d.avg_contam_sr),allKS=axis4.map(d=>d.avg_k_sr);
axis4.forEach(d=>{{sH+=`<tr><td>${{d.commodity_id}} ${{d.segment}}</td><td>${{d.n_base}}</td><td>${{hlCell(d.avg_contam_sr,allCS,4)}}</td><td>${{hlCell(d.avg_k_sr,allKS,4)}}</td></tr>`;}});
sH+='</tbody></table>';document.getElementById('sens_table').innerHTML=sH;

// Axis 5 (bar — independent unit comparison)
new Chart(document.getElementById('cons_line'),{{type:'bar',data:{{labels:labels20,datasets:[bds('Cross-Track Agreement (CTA)',axis5.map(d=>d.cta),C.cta),bds('Agreement-Shock Coincidence (ASC)',axis5.map(d=>d.asc),C.asc),bds('P_stat (Statistical Precision)',axis5.map(d=>d.p_stat),C.ps),bds('P_ml (ML Precision)',axis5.map(d=>d.p_ml),C.pm)]}},options:{{responsive:true,maintainAspectRatio:false,plugins:{{legend:{{position:'top',labels:{{boxWidth:12,font:{{size:10}}}}}}}},scales:{{x:{{ticks:{{font:{{size:8}},maxRotation:60}}}},y:{{min:0,title:{{display:true,text:'Rate'}}}}}}}}}});

let hH='<table class="eval"><thead><tr><th>Commodity</th><th>CTA</th><th>ASC</th><th>P_stat</th><th>P_ml</th><th>ESR_stat</th><th>ESR_ml</th><th>Hypothesis</th></tr></thead><tbody>';
axis5.forEach(d=>{{const b=d.hypothesis_holds===true?'<span class="hyp-true">HOLD</span>':d.hypothesis_holds===false?'<span class="hyp-false">REJECT</span>':'<span class="hyp-na">N/A</span>';hH+=`<tr><td>${{d.commodity_id}} ${{d.segment}}</td><td>${{d.cta!==null?d.cta.toFixed(3):'—'}}</td><td>${{d.asc!==null?d.asc.toFixed(3):'—'}}</td><td>${{d.p_stat!==null?d.p_stat.toFixed(3):'—'}}</td><td>${{d.p_ml!==null?d.p_ml.toFixed(3):'—'}}</td><td>${{d.esr_stat!==null?d.esr_stat.toFixed(2):'—'}}</td><td>${{d.esr_ml!==null?d.esr_ml.toFixed(2):'—'}}</td><td>${{b}}</td></tr>`;}});
hH+='</tbody></table>';document.getElementById('hyp_table').innerHTML=hH;

// Radar
const rs=[Math.min(wESR/1,1),Math.min(aSR/4,1),Math.min((aAUC-0.5)/0.4,1),Math.min(aSens/1,1),Math.min(aCTA/0.3,1)];
new Chart(document.getElementById('radar_all'),{{type:'radar',data:{{labels:['External Shock Recall','Separation Ratio','AUC (Consistency)','Stability Ratio','Cross-Track Agreement'],datasets:[{{label:'Current',data:rs,backgroundColor:'rgba(59,130,246,0.15)',borderColor:'rgba(59,130,246,0.8)',borderWidth:2,pointBackgroundColor:'rgba(59,130,246,1)',pointRadius:5}}]}},options:{{responsive:true,maintainAspectRatio:true,plugins:{{legend:{{display:false}}}},scales:{{r:{{min:0,max:1,ticks:{{stepSize:0.25,display:false}},grid:{{color:'rgba(30,41,59,0.5)'}},pointLabels:{{font:{{size:11}}}},angleLines:{{color:'rgba(30,41,59,0.3)'}}}}}}}}}});

// Verdict
const vd=[
  {{a:'Axis 1 — External Shock Recall',v:wESR.toFixed(3),i:wESR>=0.7?'Good':'Moderate — unsupervised baseline',g:wESR>=0.7?'grade-good':'grade-moderate'}},
  {{a:'Axis 2 — Separation Ratio',v:'IF='+avg(axis2.map(d=>d.sr_if)).toFixed(2)+' / LOF='+avg(axis2.map(d=>d.sr_lof)).toFixed(2)+' / SVM='+avg(axis2.map(d=>d.sr_svm)).toFixed(2),i:aSR>=2?'All models SR > 2.0':'Partial below 2.0',g:aSR>=2?'grade-good':'grade-moderate'}},
  {{a:'Axis 3 — AUC / MAE / MSE',v:'AUC='+aAUC.toFixed(3)+', MAE='+(1-aAUC).toFixed(3),i:aAUC>=0.7?'Ideal range':'Independence secured',g:aAUC>=0.7?'grade-good':'grade-moderate'}},
  {{a:'Axis 4 — Stability Ratio',v:'Contam='+aCS.toFixed(3)+' / k='+aKS.toFixed(3),i:'k robust ('+aKS.toFixed(2)+'), contam moderate ('+aCS.toFixed(2)+')',g:aSens>=0.8?'grade-good':'grade-moderate'}},
  {{a:'Axis 5 — Consensus',v:'CTA='+aCTA.toFixed(3),i:'Hypothesis holds: '+axis5.filter(d=>d.hypothesis_holds===true).length+'/'+axis5.filter(d=>d.hypothesis_holds!==null).length,g:aCTA>=0.3?'grade-good':aCTA>=0.15?'grade-moderate':'grade-weak'}},
];
let vH='<table class="eval"><thead><tr><th>Axis</th><th>Key Value</th><th>Interpretation</th><th>Verdict</th></tr></thead><tbody>';
vd.forEach(v=>{{const lb=v.g==='grade-good'?'Good':v.g==='grade-moderate'?'Moderate':'Needs Work';vH+=`<tr><td style="font-size:11px">${{v.a}}</td><td>${{v.v}}</td><td style="color:var(--text-secondary);font-size:11px">${{v.i}}</td><td><span class="grade ${{v.g}}" style="font-size:11px">${{lb}}</span></td></tr>`;}});
vH+='</tbody></table>';document.getElementById('verdict_table').innerHTML=vH;
</script>
</body>
</html>"""
    return html


# ---------------------------------------------------------------------------
# 메인
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="ML 평가 대시보드 HTML 생성")
    parser.add_argument("--run", type=str, default=None, help="특정 run 디렉토리명")
    parser.add_argument("--compare", type=str, default=None, help="비교 대상 run 디렉토리명")
    args = parser.parse_args()
    results_base = Path(os.path.dirname(os.path.abspath(__file__))) / "results"
    run_dir = results_base / args.run if args.run else results_base / "latest"
    if not run_dir.exists():
        print(f"[ERROR] 디렉토리 없음: {run_dir}"); print("  run_all_evaluation.py를 먼저 실행하세요."); sys.exit(1)
    print(f"[Dashboard] 데이터 로딩: {run_dir}")
    data = load_run_data(run_dir)
    compare_data = None
    if args.compare:
        cd = results_base / args.compare
        if cd.exists(): print(f"[Dashboard] 비교 대상: {cd}"); compare_data = load_run_data(cd)
        else: print(f"[WARNING] 비교 대상 없음: {cd}")
    html = generate_html(data, compare_data)
    op = run_dir / "dashboard.html"
    with open(op, "w", encoding="utf-8") as f: f.write(html)
    ld = results_base / "latest" / "dashboard.html"
    if run_dir != results_base / "latest" and (results_base / "latest").exists():
        with open(ld, "w", encoding="utf-8") as f: f.write(html)
    print(f"[Dashboard] 생성 완료: {op}")

if __name__ == "__main__":
    main()