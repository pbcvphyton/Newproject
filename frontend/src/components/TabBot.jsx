import { C, fmt } from "../constants";
import { Card, Loading, ErrorBox } from "./Shared";
import { useApi } from "../hooks/useApi";

export function TabBot() {
  const { data, loading, error } = useApi("/ciclos");

  if (loading) return <Loading />;
  if (error)   return <ErrorBox msg={error} />;
  if (!data)   return null;

  const u = data.ultimo;
  const s = data.stats;
  const h = data.historico || [];

  return (
    <div style={{display:"flex",flexDirection:"column",gap:16}}>
      <h2 style={{fontSize:18,fontWeight:400,color:C.bright,margin:0}}>Bot Evolutivo — Status</h2>

      <div style={{display:"grid",gridTemplateColumns:"repeat(4,1fr)",gap:12}}>
        {[
          {l:"Decisões",      v:fmt(s?.total||0)},
          {l:"Com PDF",       v:fmt(s?.com_pdf||0)},
          {l:"Com texto",     v:fmt(s?.com_texto||0)},
          {l:"Classificadas", v:fmt(s?.classificados_ia||0)},
        ].map((m,i)=>(
          <Card key={i}>
            <div style={{padding:"14px 18px"}}>
              <div style={{fontSize:10,letterSpacing:1,textTransform:"uppercase",color:C.dim,fontWeight:600}}>{m.l}</div>
              <div style={{fontSize:22,fontWeight:300,fontFamily:"monospace",color:C.bright,marginTop:6}}>{m.v}</div>
            </div>
          </Card>
        ))}
      </div>

      {u && (
        <Card>
          <div style={{padding:"16px 20px",borderBottom:`1px solid ${C.border}`,fontSize:10,letterSpacing:1.5,textTransform:"uppercase",color:C.dim,fontWeight:600}}>
            Último Ciclo (#{u.id}) — {u.status}
          </div>
          <div style={{padding:16,display:"grid",gridTemplateColumns:"repeat(3,1fr)",gap:12}}>
            {[
              {l:"Decisões novas",   v:u.decisoes_novas},
              {l:"PDFs baixados",    v:u.pdfs_baixados},
              {l:"Classificados IA", v:u.classificados_ia},
              {l:"Textos extraídos", v:u.textos_extraidos},
              {l:"Termos pesquisados",v:u.termos_pesquisados},
              {l:"Termos gerados IA",v:u.termos_novos_gerados},
            ].map((m,i)=>(
              <div key={i}>
                <div style={{fontSize:10,color:C.dim}}>{m.l}</div>
                <div style={{fontSize:16,fontFamily:"monospace",color:C.bright,marginTop:2}}>{m.v ?? 0}</div>
              </div>
            ))}
          </div>
        </Card>
      )}

      {h.length > 0 && (
        <Card style={{overflow:"hidden"}}>
          <div style={{padding:"14px 20px",borderBottom:`1px solid ${C.border}`,fontSize:10,letterSpacing:1.5,textTransform:"uppercase",color:C.dim,fontWeight:600}}>
            Histórico de Ciclos
          </div>
          <table style={{width:"100%",borderCollapse:"collapse"}}>
            <thead>
              <tr style={{borderBottom:`1px solid ${C.border}`}}>
                {["#","Status","Novas","PDFs","IA","Termos","Início"].map((h,i)=>(
                  <th key={i} style={{padding:"8px 14px",textAlign:i>=2?"right":"left",fontSize:9,color:C.dim,fontWeight:600}}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {h.slice(0,15).map(c=>(
                <tr key={c.id} style={{borderBottom:`1px solid ${C.border}`}}>
                  <td style={{padding:"8px 14px",fontFamily:"monospace",fontSize:10,color:C.dim}}>#{c.id}</td>
                  <td style={{padding:"8px 14px",fontSize:11,color:c.status==="concluido"?C.green:C.red}}>{c.status}</td>
                  <td style={{padding:"8px 14px",textAlign:"right",fontFamily:"monospace",fontSize:11}}>{c.decisoes_novas??0}</td>
                  <td style={{padding:"8px 14px",textAlign:"right",fontFamily:"monospace",fontSize:11}}>{c.pdfs_baixados??0}</td>
                  <td style={{padding:"8px 14px",textAlign:"right",fontFamily:"monospace",fontSize:11}}>{c.classificados_ia??0}</td>
                  <td style={{padding:"8px 14px",textAlign:"right",fontFamily:"monospace",fontSize:11}}>{c.termos_novos_gerados??0}</td>
                  <td style={{padding:"8px 14px",fontSize:10,color:C.dim}}>{c.inicio?.slice(0,16)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </div>
  );
}
