import { useState } from "react";
import { C } from "./constants";
import { Nav }        from "./components/Nav";
import { TabBI }      from "./components/TabBI";
import { TabRanking } from "./components/TabRanking";
import { TabLeitor }  from "./components/TabLeitor";
import { TabBot }     from "./components/TabBot";

export default function App() {
  const [tab, setTab] = useState("bi");

  return (
    <div style={{
      minHeight:"100vh", background:C.bg, color:C.text,
      fontFamily:"'IBM Plex Sans',-apple-system,sans-serif"
    }}>
      <link
        href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@300;400;500;600&family=IBM+Plex+Mono:wght@300;400;500&display=swap"
        rel="stylesheet"
      />

      <Nav tab={tab} setTab={setTab} />

      <main style={{maxWidth:1080,margin:"0 auto",padding:"28px 20px"}}>
        {tab === "bi"      && <TabBI />}
        {tab === "ranking" && <TabRanking />}
        {tab === "leitor"  && <TabLeitor />}
        {tab === "bot"     && <TabBot />}
      </main>

      <footer style={{borderTop:`1px solid ${C.border}`,marginTop:40,background:C.card}}>
        <div style={{
          maxWidth:1080,margin:"0 auto",padding:"14px 20px",
          display:"flex",justifyContent:"space-between",alignItems:"center",
          fontSize:10,color:C.dim
        }}>
          <span>JurisIntel v2 — PBCV Advocacia</span>
          <span>ESAJ/CJSG TJ-SP · Claude AI · FastAPI</span>
        </div>
      </footer>
    </div>
  );
}
