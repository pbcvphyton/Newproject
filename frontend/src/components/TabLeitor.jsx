import { useState } from "react";
import { C, fmt } from "../constants";
import { Card, Loading, ErrorBox } from "./Shared";
import { useApi } from "../hooks/useApi";

export function TabLeitor() {
  const { data, loading, error } = useApi("/decisoes?limit=200");
  const [openId, setOpenId] = useState(null);

  if (loading) return <Loading />;
  if (error)   return <ErrorBox msg={error} />;
  if (!data?.length) return (
    <div style={{padding:40,textAlign:"center",color:C.dim,fontSize:13}}>
      Nenhuma decisão classificada. Execute o pipeline para popular o banco.
    </div>
  );

  return (
    <div>
      <h2 style={{fontSize:18,fontWeight:400,color:C.bright,margin:"0 0 4px"}}>Leitor de Decisões</h2>
      <p style={{fontSize:12,color:C.dim,margin:"0 0 20px"}}>
        {data.length} decisões carregadas — classificadas automaticamente por IA.
      </p>

      <div style={{display:"flex",flexDirection:"column",gap:8}}>
        {data.map(d => {
          const isOpen = openId === d.id;
          const res = (d.resultado||"").toLowerCase();
          const isProv = res.includes("provido") && !res.includes("não");
          const cor = isProv ? C.green : C.red;
          const corPale = isProv ? C.greenPale : C.redPale;

          return (
            <Card key={d.id} style={{overflow:"hidden"}}>
              {/* Header */}
              <button onClick={()=>setOpenId(isOpen?null:d.id)} style={{
                width:"100%",padding:"14px 20px",background:"none",border:"none",
                cursor:"pointer",display:"flex",alignItems:"center",justifyContent:"space-between",textAlign:"left"
              }}>
                <div style={{display:"flex",alignItems:"center",gap:14}}>
                  <div style={{
                    minWidth:44,height:44,borderRadius:8,background:corPale,
                    display:"flex",flexDirection:"column",alignItems:"center",justifyContent:"center",
                    border:`1px solid ${isProv?C.greenBorder:C.redBorder}`
                  }}>
                    <span style={{fontSize:11,fontWeight:600,fontFamily:"monospace",color:cor,lineHeight:1}}>
                      {d.resultado||"?"}
                    </span>
                  </div>
                  <div>
                    <div style={{fontSize:13,color:C.bright,fontWeight:500}}>
                      {d.tese_principal || d.tipo_acao || d.classe_processual || d.numero_processo}
                    </div>
                    <div style={{fontSize:11,color:C.dim,marginTop:2}}>
                      {d.area_direito||""} · {d.orgao_julgador||""} · {d.relator||""}
                    </div>
                  </div>
                </div>
                <span style={{fontSize:16,color:C.dim,transition:"transform .2s",
                  transform:isOpen?"rotate(180deg)":"none"}}>&#8964;</span>
              </button>

              {/* Expanded */}
              {isOpen && (
                <div style={{borderTop:`1px solid ${C.border}`}}>
                  {/* Ementa */}
                  {d.ementa && (
                    <div style={{padding:"16px 24px",borderBottom:`1px solid ${C.border}`}}>
                      <div style={{fontSize:9,fontWeight:600,color:C.blue,letterSpacing:1,textTransform:"uppercase",marginBottom:6}}>Ementa</div>
                      <p style={{fontSize:12,color:C.bright,lineHeight:1.7,margin:0,fontWeight:300}}>{d.ementa}</p>
                    </div>
                  )}

                  {/* Resumo IA */}
                  {d.resumo_ia && (
                    <div style={{padding:"16px 24px",borderBottom:`1px solid ${C.border}`,background:"#fafbfc"}}>
                      <div style={{fontSize:9,fontWeight:600,color:C.green,letterSpacing:1,textTransform:"uppercase",marginBottom:6}}>Resumo IA</div>
                      <p style={{fontSize:12,color:C.bright,lineHeight:1.7,margin:0,fontWeight:300}}>{d.resumo_ia}</p>
                    </div>
                  )}

                  {/* Dados estruturados */}
                  <div style={{display:"grid",gridTemplateColumns:"1fr 1fr 1fr",borderBottom:`1px solid ${C.border}`}}>
                    {[
                      {l:"Processo",v:d.numero_processo},
                      {l:"Resultado",v:d.resultado_detalhado||d.resultado},
                      {l:"Comarca",v:d.comarca},
                      {l:"Autor",v:`${d.autor_nome||"—"} (${d.autor_tipo||"?"})`},
                      {l:"Réu",v:`${d.reu_nome||"—"} (${d.reu_tipo||"?"})`},
                      {l:"Dano Moral",v:d.dano_moral_valor?`R$ ${fmt(d.dano_moral_valor)}`:"—"},
                    ].map((item,i)=>(
                      <div key={i} style={{
                        padding:"12px 20px",
                        borderRight:i%3<2?`1px solid ${C.border}`:"none",
                        borderBottom:i<3?`1px solid ${C.border}`:"none"
                      }}>
                        <div style={{fontSize:9,color:C.dim,letterSpacing:0.5}}>{item.l}</div>
                        <div style={{fontSize:12,color:C.bright,marginTop:4,fontWeight:400}}>{item.v||"—"}</div>
                      </div>
                    ))}
                  </div>

                  {/* Fundamentação e precedentes */}
                  <div style={{padding:"12px 24px",display:"flex",gap:20,fontSize:10,color:C.dim,background:"#fafbfc"}}>
                    {d.fundamentacao_legal && <span>Fund.: {d.fundamentacao_legal}</span>}
                    {d.precedentes_citados && <span>Prec.: {d.precedentes_citados}</span>}
                    <span>{d.data_julgamento||""}</span>
                  </div>
                </div>
              )}
            </Card>
          );
        })}
      </div>
    </div>
  );
}
