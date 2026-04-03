import { useMemo } from "react";
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell, AreaChart, Area, CartesianGrid,
} from "recharts";
import { C, PIE_C, fmt } from "../constants";
import { Tip, Card, StatCard, Loading, ErrorBox } from "./Shared";
import { useApi } from "../hooks/useApi";

const LABEL = {fontSize:10,letterSpacing:1.5,textTransform:"uppercase",color:C.dim,fontWeight:600};

export function TabBI() {
  const { data, loading, error } = useApi("/bi");

  const { totals, sorted, byArea, tendencia } = useMemo(() => {
    if (!data) return {};
    const stats = data.stats;
    const ranking = data.top_tipos || [];

    const sorted = [...ranking].sort((a,b) => (b.taxa||0)-(a.taxa||0));
    const byArea  = data.por_area || [];
    const tendencia = data.tendencia_mensal || [];
    const totals = {
      total: stats.total,
      classificados: stats.classificados_ia,
      taxa: byArea.length
        ? Math.round(byArea.reduce((s,a)=>s+(a.pos||0),0) /
            Math.max(byArea.reduce((s,a)=>s+(a.total||0),0),1)*100)
        : 0,
    };
    return { totals, sorted, byArea, tendencia };
  }, [data]);

  if (loading) return <Loading />;
  if (error)   return <ErrorBox msg={error} />;
  if (!data)   return null;

  const melhor = sorted?.[0];

  return (
    <div style={{display:"flex",flexDirection:"column",gap:16}}>
      {/* KPIs */}
      <div style={{display:"grid",gridTemplateColumns:"repeat(4,1fr)",gap:12}}>
        <StatCard label="Decisões Analisadas"  value={fmt(totals.total)}         sub="banco SQLite" />
        <StatCard label="Classificadas por IA" value={fmt(totals.classificados)}  sub="Claude claude-sonnet-4-6" accent />
        <StatCard label="Taxa Geral de Êxito"  value={`${totals.taxa}%`}          sub="por área ativa" accent />
        <StatCard label="Maior Oportunidade"
          value={melhor?.tipo_acao?.split("—")[0]?.trim() || "—"}
          sub={melhor ? `${melhor.taxa}% êxito` : "coletando…"} accent />
      </div>

      {/* Bar + Pie */}
      <div style={{display:"grid",gridTemplateColumns:"5fr 3fr",gap:12}}>
        <Card>
          <div style={{padding:"14px 20px",borderBottom:`1px solid ${C.border}`,...LABEL}}>
            Favoráveis vs Desfavoráveis por Tipo
          </div>
          <div style={{padding:"8px 4px"}}>
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={sorted} layout="vertical" margin={{left:4,right:16}} barGap={2}>
                <XAxis type="number" tick={{fill:C.dim,fontSize:9}} axisLine={false} tickLine={false}/>
                <YAxis type="category" dataKey="tipo_acao" width={180}
                  tick={{fill:C.text,fontSize:9}} axisLine={false} tickLine={false}/>
                <Tooltip content={<Tip/>} cursor={{fill:"rgba(26,63,111,0.03)"}}/>
                <Bar dataKey="pos" name="Favoráveis"    fill={C.green} radius={[0,4,4,0]} barSize={8} opacity={0.85}/>
                <Bar dataKey="neg" name="Desfavoráveis" fill={C.red}   radius={[0,4,4,0]} barSize={8} opacity={0.25}/>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>

        <div style={{display:"flex",flexDirection:"column",gap:12}}>
          <Card style={{flex:1,overflow:"hidden"}}>
            <div style={{padding:"14px 20px",borderBottom:`1px solid ${C.border}`,...LABEL}}>Volume por Área</div>
            <div style={{padding:16,display:"flex",flexDirection:"column",alignItems:"center"}}>
              <ResponsiveContainer width="100%" height={160}>
                <PieChart>
                  <Pie data={byArea.map(a=>({name:a.name,value:a.total}))}
                    cx="50%" cy="50%" innerRadius={38} outerRadius={65}
                    dataKey="value" stroke={C.card} strokeWidth={3}>
                    {byArea.map((_,i)=><Cell key={i} fill={PIE_C[i%PIE_C.length]}/>)}
                  </Pie>
                  <Tooltip content={<Tip/>}/>
                </PieChart>
              </ResponsiveContainer>
              <div style={{display:"flex",flexWrap:"wrap",gap:"4px 12px",justifyContent:"center"}}>
                {byArea.map((a,i)=>(
                  <div key={a.name} style={{display:"flex",alignItems:"center",gap:5,fontSize:10,color:C.text}}>
                    <div style={{width:7,height:7,borderRadius:2,background:PIE_C[i%PIE_C.length]}}/>
                    {a.name}
                  </div>
                ))}
              </div>
            </div>
          </Card>

          {/* Tendência mensal */}
          <Card style={{overflow:"hidden"}}>
            <div style={{padding:"14px 20px",borderBottom:`1px solid ${C.border}`,...LABEL}}>Tendência Mensal</div>
            <div style={{padding:"8px 4px"}}>
              <ResponsiveContainer width="100%" height={100}>
                <AreaChart data={tendencia} margin={{left:0,right:8,top:8}}>
                  <defs>
                    <linearGradient id="grd" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%"   stopColor={C.green} stopOpacity={0.15}/>
                      <stop offset="100%" stopColor={C.green} stopOpacity={0}/>
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke={C.border}/>
                  <XAxis dataKey="mes" tick={{fill:C.dim,fontSize:8}} axisLine={false} tickLine={false}/>
                  <YAxis tick={{fill:C.dim,fontSize:9}} axisLine={false} tickLine={false} width={28}/>
                  <Tooltip content={<Tip/>}/>
                  <Area type="monotone" dataKey="total" name="Total"
                    stroke={C.green} fill="url(#grd)" strokeWidth={1.5}
                    dot={{fill:C.green,r:2,strokeWidth:0}}/>
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </Card>
        </div>
      </div>

      {/* Top Relatores */}
      {data.top_relatores?.length > 0 && (
        <Card>
          <div style={{padding:"14px 20px",borderBottom:`1px solid ${C.border}`,...LABEL}}>Top Relatores</div>
          <div style={{overflowX:"auto"}}>
            <table style={{width:"100%",borderCollapse:"collapse"}}>
              <thead>
                <tr style={{borderBottom:`1px solid ${C.border}`}}>
                  {["Relator","Total","Taxa Provido"].map((h,i)=>(
                    <th key={i} style={{padding:"8px 16px",textAlign:i>0?"right":"left",...LABEL,fontSize:9}}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {data.top_relatores.slice(0,10).map((r,i)=>(
                  <tr key={i} style={{borderBottom:`1px solid ${C.border}`}}>
                    <td style={{padding:"10px 16px",fontSize:12,color:C.bright}}>{r.relator}</td>
                    <td style={{padding:"10px 16px",textAlign:"right",fontFamily:"monospace",fontSize:11,color:C.dim}}>{fmt(r.total)}</td>
                    <td style={{padding:"10px 16px",textAlign:"right",fontFamily:"monospace",fontSize:12,fontWeight:600,
                      color:r.taxa_provido>=60?C.green:r.taxa_provido>=45?"#d69e2e":C.red}}>
                      {r.taxa_provido}%
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </div>
  );
}
