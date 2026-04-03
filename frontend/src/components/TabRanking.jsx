import { C, fmt } from "../constants";
import { Card, TaxaBar, Loading, ErrorBox } from "./Shared";
import { useApi } from "../hooks/useApi";

const LABEL = {fontSize:9,letterSpacing:1.5,textTransform:"uppercase",color:C.dim,fontWeight:600};

export function TabRanking() {
  const { data, loading, error } = useApi("/ranking");

  if (loading) return <Loading />;
  if (error)   return <ErrorBox msg={error} />;
  if (!data?.length) return (
    <div style={{padding:40,textAlign:"center",color:C.dim,fontSize:13}}>
      Nenhum dado ainda — execute o pipeline para coletar e classificar decisões.
    </div>
  );

  return (
    <div>
      <h2 style={{fontSize:18,fontWeight:400,color:C.bright,margin:"0 0 16px"}}>
        Ranking por Taxa de Êxito
      </h2>
      <Card style={{overflow:"hidden"}}>
        <table style={{width:"100%",borderCollapse:"collapse"}}>
          <thead>
            <tr style={{borderBottom:`1px solid ${C.border}`}}>
              {["#","Tipo / Tese","Área","Êxito","","Ganhas","Perdidas","Total","Valor Médio"].map((h,i)=>(
                <th key={i} style={{
                  padding:"10px 14px", textAlign:i>=3?"right":"left", ...LABEL
                }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.map((d,i) => (
              <tr key={i}
                style={{borderBottom:`1px solid ${C.border}`,transition:"background .1s"}}
                onMouseEnter={e=>e.currentTarget.style.background=C.bluePale}
                onMouseLeave={e=>e.currentTarget.style.background="transparent"}>
                <td style={{padding:"12px 14px",fontFamily:"monospace",fontSize:10,color:C.dim}}>
                  {String(i+1).padStart(2,"0")}
                </td>
                <td style={{padding:"12px 14px",fontSize:12,color:C.bright,fontWeight:500,maxWidth:220}}>
                  {d.tipo}
                </td>
                <td style={{padding:"12px 14px",fontSize:11,color:C.dim}}>{d.area_direito}</td>
                <td style={{padding:"12px 14px",textAlign:"right",fontFamily:"monospace",fontSize:13,fontWeight:600,
                  color:d.taxa>=60?C.green:d.taxa>=45?"#d69e2e":C.red}}>
                  {d.taxa}%
                </td>
                <td style={{padding:"12px 4px"}}>
                  <TaxaBar taxa={d.taxa}/>
                </td>
                <td style={{padding:"12px 14px",textAlign:"right",fontFamily:"monospace",fontSize:11,color:C.green}}>
                  {fmt(d.pos)}
                </td>
                <td style={{padding:"12px 14px",textAlign:"right",fontFamily:"monospace",fontSize:11,color:C.red,opacity:0.5}}>
                  {fmt(d.neg)}
                </td>
                <td style={{padding:"12px 14px",textAlign:"right",fontFamily:"monospace",fontSize:11,color:C.dim}}>
                  {fmt(d.total)}
                </td>
                <td style={{padding:"12px 14px",textAlign:"right",fontFamily:"monospace",fontSize:10,color:C.dim}}>
                  {d.valor_medio_condenacao
                    ? `R$ ${fmt(Math.round(d.valor_medio_condenacao))}`
                    : "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </div>
  );
}
