import { C } from "../constants";

const TABS = [
  { k:"bi",      l:"BI"              },
  { k:"ranking", l:"Ranking"         },
  { k:"leitor",  l:"Leitor"          },
  { k:"bot",     l:"Bot / Status"    },
];

export function Nav({ tab, setTab }) {
  return (
    <nav style={{
      background:C.card, borderBottom:`1px solid ${C.border}`,
      padding:"0 28px", height:52,
      display:"flex", alignItems:"center", justifyContent:"space-between",
      boxShadow:"0 1px 3px rgba(0,0,0,0.04)", position:"sticky", top:0, zIndex:100,
    }}>
      {/* Logo */}
      <div style={{display:"flex",alignItems:"center",gap:10}}>
        <div style={{
          width:28, height:28, borderRadius:7,
          background:`linear-gradient(135deg,${C.blue},${C.blueLight})`,
          display:"flex", alignItems:"center", justifyContent:"center",
          color:"#fff", fontSize:13, fontWeight:600,
        }}>J</div>
        <span style={{fontSize:14,fontWeight:600,color:C.bright}}>JurisIntel</span>
        <span style={{fontSize:9,letterSpacing:2,color:C.dim,textTransform:"uppercase",marginLeft:4}}>TJ-SP</span>
      </div>

      {/* Tabs */}
      <div style={{display:"flex",gap:2,background:C.bg,borderRadius:8,padding:3}}>
        {TABS.map(t => (
          <button key={t.k} onClick={() => setTab(t.k)} style={{
            padding:"6px 16px", borderRadius:6, fontSize:11, fontWeight:500,
            border:"none", cursor:"pointer", transition:"all .15s",
            background: tab === t.k ? C.card : "transparent",
            color:       tab === t.k ? C.blue : C.dim,
            boxShadow:   tab === t.k ? "0 1px 3px rgba(0,0,0,0.06)" : "none",
          }}>{t.l}</button>
        ))}
      </div>
    </nav>
  );
}
