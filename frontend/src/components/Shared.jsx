import { C, fmt } from "../constants";

/* ── Tooltip Recharts ── */
export function Tip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  return (
    <div style={{
      background:"#fff", border:`1px solid ${C.border}`, borderRadius:8,
      padding:"10px 14px", fontSize:11, color:C.text,
      boxShadow:"0 4px 12px rgba(0,0,0,0.08)"
    }}>
      <div style={{color:C.bright,fontWeight:500,marginBottom:4}}>{label}</div>
      {payload.map((p,i)=>(
        <div key={i} style={{color:p.color,marginTop:2}}>{p.name}: {fmt(p.value)}</div>
      ))}
    </div>
  );
}

/* ── Card base ── */
export function Card({ children, style={} }) {
  return (
    <div style={{
      background:C.card, border:`1px solid ${C.border}`,
      borderRadius:10, boxShadow:"0 1px 3px rgba(0,0,0,0.04)", ...style
    }}>
      {children}
    </div>
  );
}

/* ── StatCard ── */
export function StatCard({ label, value, sub, accent=false }) {
  const LABEL = {fontSize:10,letterSpacing:1.5,textTransform:"uppercase",color:C.dim,fontWeight:600};
  return (
    <Card style={accent ? {borderColor:C.green} : {}}>
      <div style={{padding:"16px 20px"}}>
        <div style={LABEL}>{label}</div>
        <div style={{
          fontSize:24, fontWeight:300,
          fontFamily:"'IBM Plex Mono',monospace",
          color: accent ? C.green : C.bright, marginTop:8
        }}>{value}</div>
        <div style={{fontSize:10,color:C.dim,marginTop:4}}>{sub}</div>
      </div>
    </Card>
  );
}

/* ── Badge resultado ── */
export function Badge({ res }) {
  const isProv   = res === "Provido";
  const isParcial= res === "Parcial";
  const bg  = isProv ? C.greenPale : isParcial ? "#fffbeb" : C.redPale;
  const clr = isProv ? C.green     : isParcial ? "#d69e2e" : C.red;
  const brd = isProv ? C.greenBorder : isParcial ? "#fde68a" : C.redBorder;
  return (
    <span style={{
      padding:"3px 8px", borderRadius:4, fontSize:10, fontWeight:500,
      background:bg, color:clr, border:`1px solid ${brd}`
    }}>{res}</span>
  );
}

/* ── Barra de progresso ── */
export function TaxaBar({ taxa }) {
  const cor = taxa >= 60 ? C.green : taxa >= 45 ? "#d69e2e" : C.red;
  return (
    <div style={{height:4,borderRadius:2,background:C.redBorder,overflow:"hidden",width:100}}>
      <div style={{height:4,borderRadius:2,background:cor,width:`${taxa}%`,transition:"width .5s"}}/>
    </div>
  );
}

/* ── Loading spinner ── */
export function Loading({ texto="Carregando…" }) {
  return (
    <div style={{display:"flex",alignItems:"center",justifyContent:"center",padding:48,color:C.dim,fontSize:13}}>
      <span style={{marginRight:8,fontSize:18,animation:"spin 1s linear infinite",display:"inline-block"}}>⟳</span>
      {texto}
    </div>
  );
}

/* ── Error box ── */
export function ErrorBox({ msg }) {
  return (
    <div style={{padding:20,background:C.redPale,border:`1px solid ${C.redBorder}`,borderRadius:8,color:C.red,fontSize:13}}>
      ⚠ Erro ao carregar dados: {msg}
    </div>
  );
}
