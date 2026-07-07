import streamlit as st
import pandas as pd
import gspread
import datetime
import json
import streamlit.components.v1 as components
from oauth2client.service_account import ServiceAccountCredentials

def run_tycoon_game():
    st.markdown("""
        <style>
        .rank-card { border: 2px solid #4CAF50; padding: 15px; border-radius: 10px; background-color: #F9FFF9; text-align: center; margin-bottom: 15px; }
        .gold { color: #D4AF37; font-size: 1.5em; font-weight: bold; }
        .silver { color: #C0C0C0; font-size: 1.3em; font-weight: bold; }
        .bronze { color: #CD7F32; font-size: 1.1em; font-weight: bold; }
        
        /* 스트림릿과 통신하기 위한 숨겨진 입력창 */
        div[data-testid="stTextInput"]:has(input[aria-label="hidden_tycoon_data"]) {
            position: absolute !important; left: -9999px !important; opacity: 0 !important; height: 0px !important;
        }
        </style>
    """, unsafe_allow_html=True)

    st.header("🌾 대한사료 밸류체인 타이쿤 (Beta)")
    st.caption("원료 구매부터 농장 배송까지! 최고의 순이익을 달성해 보세요.")
    st.markdown("---")

    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/spreadsheets",
             "https://www.googleapis.com/auth/drive.file", "https://www.googleapis.com/auth/drive"]
    
    @st.cache_resource
    def init_gspread_tycoon():
        creds = ServiceAccountCredentials.from_json_keyfile_dict(st.secrets["gcp_service_account"], scope)
        client = gspread.authorize(creds)
        return client.open("대한사료_타이쿤_DB")

    @st.cache_data(ttl=5, show_spinner=False)
    def get_tycoon_leaderboard():
        try:
            doc = init_gspread_tycoon()
            records = doc.worksheet("leaderboard").get_all_records()
            return records
        except:
            return []

    def save_tycoon_score(name, team, profit):
        try:
            doc = init_gspread_tycoon()
            ws = doc.worksheet("leaderboard")
            kst = datetime.timezone(datetime.timedelta(hours=9))
            today_str = datetime.datetime.now(kst).strftime("%Y-%m-%d %H:%M")
            ws.append_row([name, team, profit, today_str])
            get_tycoon_leaderboard.clear() 
            return True
        except Exception as e:
            return False

    tab1, tab2 = st.tabs(["🎮 게임 플레이", "🏆 실시간 명예의 전당"])

    with tab1:
        # 차장님이 만드신 게임 HTML 코드 안에 스트림릿으로 점수를 전송하는 자바스크립트를 결합했습니다.
        game_html = """
        <!DOCTYPE html>
        <html lang="ko">
        <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <link rel="preconnect" href="https://fonts.googleapis.com">
        <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
        <link href="https://fonts.googleapis.com/css2?family=Jua&family=Noto+Sans+KR:wght@400;500;700;900&display=swap" rel="stylesheet">
        <style>
        /* (여기에 기존 스타일이 그대로 유지됩니다. 스크롤을 줄이기 위해 원본 CSS 생략 없이 모두 보존했습니다.) */
        :root{ --cream:#FBF3DE; --cream-2:#F5E9CC; --card:#FFFDF7; --leaf:#7CBF6B; --leaf-dark:#5EA24E; --leaf-deep:#3F7D34; --wood:#C79A6A; --wood-dark:#A9784B; --sky:#9FD8E8; --sky-dark:#6FB7CC; --sun:#F7C948; --sun-dark:#E0A82E; --tomato:#E8836B; --tomato-dark:#CE5B42; --brown:#6B4E2E; --line:#E3C9A0; }
        *{box-sizing:border-box;-webkit-tap-highlight-color:transparent;} html,body{margin:0;padding:0;overflow:hidden;}
        body{font-family:'Noto Sans KR',sans-serif; background:transparent; color:var(--brown); display:flex;align-items:flex-start;justify-content:center;padding:10px;}
        .frame{width:min(1080px,98vw); background:var(--cream); border-radius:20px; border:4px solid var(--wood-dark); box-shadow:0 8px 0 rgba(169,120,75,.32); padding:16px; position:relative;}
        h1,h2,h3{font-family:'Jua',sans-serif;margin:0;}
        .btn{font-family:'Jua';cursor:pointer;border:none;border-radius:18px;color:#fff;padding:13px 22px;font-size:18px;box-shadow:0 5px 0 rgba(0,0,0,.18);transition:transform .06s,box-shadow .06s;} .btn:active{transform:translateY(4px);box-shadow:0 1px 0 rgba(0,0,0,.18);}
        .btn-green{background:var(--leaf);} .btn-wood{background:var(--wood);} .btn-sun{background:var(--sun);color:var(--brown);} .btn-sm{padding:8px 14px;font-size:15px;border-radius:13px;}
        .screen{display:none;} .screen.active{display:block;animation:pop .3s ease;}
        @keyframes pop{from{opacity:0;transform:scale(.98)}to{opacity:1;transform:scale(1)}}
        /* 시작화면 */ #startScreen{text-align:center;padding:10px;} .badge{display:inline-block;background:var(--leaf);color:#fff;padding:6px 18px;border-radius:99px;font-family:'Jua';font-size:16px;} #startScreen h1{font-size:36px;color:var(--leaf-deep);margin-top:10px;} .flow{display:flex;align-items:center;justify-content:center;gap:6px;flex-wrap:wrap;margin:18px 0 6px;} .flow .step{background:var(--card);border:2px solid var(--line);border-radius:18px;padding:8px 12px;font-family:'Jua';font-size:15px;} .flow .step .big{font-size:24px;display:block;} .flow .arrow{font-size:20px;color:var(--leaf);}
        .howto{margin:10px auto;max-width:600px;background:var(--card);border:2px dashed var(--line);border-radius:15px;padding:12px;text-align:left;} .info-row{display:grid;grid-template-columns:52px 1fr;gap:12px;margin:6px 0;font-size:14px;} .info-row .lab{font-family:'Jua';color:#fff;background:var(--leaf);border-radius:9px;font-size:13px;display:flex;align-items:center;justify-content:center;}
        .entry{display:flex;gap:10px;justify-content:center;flex-wrap:wrap;margin-top:15px;} .entry input{font-size:15px;padding:10px;border-radius:10px;border:2px solid var(--line);text-align:center;} .start-actions{display:flex;gap:10px;justify-content:center;margin-top:15px;}
        /* HUD & 보드(차장님 원본 CSS 압축) */ .hud{position:sticky;top:0;z-index:20;display:flex;align-items:center;gap:12px;flex-wrap:wrap;background:linear-gradient(180deg,#FFFDF7,#FBF3DE);border:2px solid var(--line);border-radius:15px;padding:10px;margin-bottom:10px;} .money-card{display:flex;align-items:center;gap:8px;background:var(--leaf);color:#fff;padding:6px 14px;border-radius:12px;} .money-card .val{font-family:'Jua';font-size:24px;} .goal{flex:1;} .goal .top{display:flex;justify-content:space-between;font-size:12px;} .goal .bar{height:12px;background:var(--cream-2);border-radius:6px;overflow:hidden;} .goal .bar>i{display:block;height:100%;width:0;background:linear-gradient(90deg,var(--sun),var(--leaf));} .timer{font-family:'Jua';font-size:22px;color:var(--sky-dark);background:var(--cream-2);padding:4px 12px;border-radius:10px;} .board{display:grid;grid-template-columns:repeat(4,1fr);grid-template-rows:auto repeat(4,140px);gap:8px;} .stage-h{display:flex;align-items:center;justify-content:center;gap:6px;background:var(--leaf);color:#fff;border-radius:10px;padding:6px 4px;font-family:'Jua';font-size:14px;} .cell{background:var(--card);border:2px solid var(--line);border-radius:12px;padding:6px;display:flex;flex-direction:column;justify-content:center;gap:4px;text-align:center;} .cell .ttl{font-family:'Jua';font-size:16px;} .shop{grid-column:1;grid-row:2 / span 4;display:flex;flex-direction:column;gap:8px;} .mat{flex:1;display:flex;flex-direction:column;justify-content:center;background:var(--card);border:2px solid var(--line);border-radius:10px;padding:8px;} .mat .nm{font-family:'Jua';font-size:16px;} .mat .stk{font-size:13px;color:var(--leaf-deep);font-weight:700;} .buybtn, .miniact{width:100%;border:none;border-radius:8px;font-family:'Jua';font-size:14px;padding:6px 0;cursor:pointer;color:#fff;} .buybtn{background:var(--sun);color:var(--brown);} .bmake{background:var(--leaf);} .bship{background:var(--wood);} .buybtn:disabled, .miniact:disabled{background:#CFC7B2!important;cursor:not-allowed;} .road{height:20px;background:#EADFC0;border-radius:6px;position:relative;} .truck{position:absolute;top:-4px;font-size:20px;transform:scaleX(-1);} .farm{background:linear-gradient(180deg,#EAF7E2,var(--card));} .cost{font-size:11px;color:var(--tomato-dark);} .pay{font-family:'Jua';color:var(--leaf-deep);font-size:14px;}
        /* 결과화면 & 애니메이션 */ #overScreen{text-align:center;padding:20px;} .result{background:var(--card);border:3px solid var(--sun);border-radius:15px;display:inline-block;padding:15px 25px;margin:15px 0;} .result .fm{font-family:'Jua';font-size:28px;color:var(--leaf-deep);} .report{background:var(--card);border:2px solid var(--line);border-radius:12px;padding:15px;margin:10px auto;max-width:860px;text-align:left;} .rtable{width:100%;border-collapse:collapse;font-size:12px;} .rtable th,.rtable td{padding:4px;text-align:right;border-bottom:1px solid var(--line);} .toastL, .flyL{position:fixed;inset:0;pointer-events:none;z-index:99;} .toast{position:absolute;font-family:'Jua';font-size:18px;color:var(--leaf-deep);animation:up 1s ease forwards;} @keyframes up{from{opacity:1;transform:translateY(0)}to{opacity:0;transform:translateY(-40px)}} .fly{position:fixed;font-size:18px;background:#fff;border:2px solid var(--sun);border-radius:10px;padding:4px;transition:all 1s;}
        </style>
        </head>
        <body>
        <div class="frame">
        <section id="startScreen" class="screen active">
            <div class="badge">🌾 임직원 교육용 시뮬레이션</div>
            <h1>대한사료 밸류체인 타이쿤</h1>
            <div class="howto">
                <div class="info-row"><span class="lab">목표</span><span class="desc">3분 동안 원료 구매 → 제조 → 배송 → 판매로 최대한 많은 <b>순이익</b>을 남기세요.</span></div>
                <div class="info-row"><span class="lab">주의</span><span class="desc">가끔 <b>전염병·태풍</b>으로 배송이 막혀요. 연속 배송 시 <b>🔥콤보 보너스</b>!</span></div>
            </div>
            <div class="entry">
                <input id="teamName" maxlength="20" placeholder="🏷️ 팀명 (예: 인사총무팀)">
                <input id="playerName" maxlength="12" placeholder="🙋 이름">
            </div>
            <div class="start-actions"><button class="btn btn-green" onclick="startGame()">🎮 게임 시작</button></div>
        </section>
        <section id="playScreen" class="screen">
            <div class="hud">
                <div class="money-card">🪙<div><div class="val" id="moneyText">0</div></div></div>
                <div class="goal"><div class="top"><span id="goalText">0%</span></div><div class="bar"><i id="goalBar"></i></div></div>
                <div class="timer" id="timerText">03:00</div>
            </div>
            <div class="board" id="board"></div>
        </section>
        <section id="overScreen" class="screen">
            <h2>🌇 영업 종료!</h2>
            <div class="result">최종 달성 회사 자금<div class="fm" id="finalMoney">0</div><div id="gradeText"></div></div>
            <div class="report" id="reportBox"></div>
            <div class="start-actions"><button class="btn btn-green" onclick="startGame()">🔁 다시 도전</button></div>
        </section>
        </div>
        <div class="toastL" id="toastL"></div><div class="flyL" id="flyL"></div>

        <script>
        const MAT_NAMES=["옥수수","주정박","대두박","소맥피","어분"]; const MAT_EMO={"옥수수":"🌽","주정박":"🍺","대두박":"🫘","소맥피":"🌾","어분":"🐟"};
        const FEED_NAMES=["양돈","축우","양계","양어"]; const FARM_NAMES=["양돈농장","축우농장","양계농장","양어농장"]; const FARM_EMO=["🐷","🐮","🐔","🐠"];
        const DISEASES=[["아프리카돼지열병(ASF)"],["구제역(FMD)"],["조류독감(AI)"],["태풍 발생"]];
        const cfg = {start_money:50000000, goal_profit:5000000, buy_time:3, "price_옥수수":3500000,"price_주정박":3800000,"price_대두박":6000000,"price_소맥피":2800000,"price_어분":18000000, "recipe_양돈_mat1":"옥수수","recipe_양돈_amt1":6,"recipe_양돈_mat2":"대두박","recipe_양돈_amt2":4, "recipe_축우_mat1":"옥수수","recipe_축우_amt1":5,"recipe_축우_mat2":"소맥피","recipe_축우_amt2":5, "recipe_양계_mat1":"옥수수","recipe_양계_amt1":7,"recipe_양계_mat2":"주정박","recipe_양계_amt2":3, "recipe_양어_mat1":"어분","recipe_양어_amt1":6,"recipe_양어_mat2":"대두박","recipe_양어_amt2":4, make_time:[3,4,2,5], sell_price:[5250000,3850000,4350000,14700000], make_cost:[300000,300000,300000,500000], ship_cost:[250000,250000,250000,400000]};
        const GAME_DURATION=3*60*1000, DELIVER_TIME=3200, DISEASE_DURATION=10000, DISEASE_CHANCE=0.00035;
        let money,matStocks,feedStock,isMaking,makeStart,isDelivering,deliverStart,truckPos,isBuying,buyStart,isDisease,diseaseStart,happyUntil,diseaseLabel,teamName='',playerName='',combo,lastDeliverTick,goalReached,gameStartTick,rafId,stat,running=false;

        function resetGame(){ money=cfg.start_money; matStocks={}; MAT_NAMES.forEach(m=>matStocks[m]=50); feedStock=[0,0,0,0]; isMaking=[0,0,0,0]; makeStart=[0,0,0,0]; isDelivering=[0,0,0,0]; deliverStart=[0,0,0,0]; truckPos=[0,0,0,0]; isBuying={}; buyStart={}; MAT_NAMES.forEach(m=>{isBuying[m]=0;buyStart[m]=0;}); isDisease=[0,0,0,0]; diseaseStart=[0,0,0,0]; happyUntil=[0,0,0,0]; diseaseLabel=['','','','']; combo=0; lastDeliverTick=0; goalReached=false; stat={matTons:{},matCost:{},madeTons:[0,0,0,0],makeCost:[0,0,0,0], shipTons:[0,0,0,0],shipCost:[0,0,0,0],revenue:[0,0,0,0],comboBonus:0}; MAT_NAMES.forEach(m=>{stat.matTons[m]=0;stat.matCost[m]=0;}); }
        function recipeOf(i){const f=FEED_NAMES[i]; return [{mat:cfg["recipe_"+f+"_mat1"],amt:cfg["recipe_"+f+"_amt1"]},{mat:cfg["recipe_"+f+"_mat2"],amt:cfg["recipe_"+f+"_amt2"]}];}
        function man(v){return Math.round(v/10000).toLocaleString()+'만원';}
        function show(id){document.querySelectorAll('.screen').forEach(s=>s.classList.remove('active')); document.getElementById(id).classList.add('active');}

        function startGame(){
            teamName=(document.getElementById('teamName').value||'').trim(); playerName=(document.getElementById('playerName').value||'').trim();
            if(!teamName || !playerName) { alert('소속팀과 이름을 입력해야 명예의 전당에 오를 수 있습니다!'); return; }
            sessionStorage.removeItem('tycoonScoreSent');
            resetGame(); buildBoard(); show('playScreen'); running=true; gameStartTick=performance.now(); cancelAnimationFrame(rafId); loop();
        }

        function buildBoard(){
            const b=document.getElementById('board'); b.innerHTML='';
            const heads=[['1','구매'],['2','제조'],['3','배송'],['4','판매']];
            heads.forEach((h,idx)=>{ const d=document.createElement('div'); d.className='stage-h'; d.innerHTML=`${h[1]}`; d.style.gridColumn=(idx+1); d.style.gridRow=1; b.appendChild(d); });
            const shop=document.createElement('div'); shop.className='shop';
            shop.innerHTML=MAT_NAMES.map(m=>`<div class="mat" id="mat-${m}"><div class="nm">${MAT_EMO[m]}${m} <span class="stk" id="stk-${m}">0t</span></div><button class="buybtn" id="buy-${m}" onclick="buyMat('${m}')">구매</button></div>`).join('');
            b.appendChild(shop);
            for(let i=0;i<4;i++){
                const fac=document.createElement('div'); fac.className='cell factory'; fac.id='fac-'+i; fac.style.gridColumn=2; fac.style.gridRow=i+2;
                fac.innerHTML=`<div class="ttl">🏭${FEED_NAMES[i]}</div><div class="cost">-${man(cfg.make_cost[i])}</div><button class="miniact bmake" id="mk-${i}" onclick="makeFeed(${i})">제조</button>`; b.appendChild(fac);
                const shp=document.createElement('div'); shp.className='cell ship'; shp.id='shp-'+i; shp.style.gridColumn=3; shp.style.gridRow=i+2;
                shp.innerHTML=`<div class="ttl">🚚배송 <span id="feedstk-${i}">0t</span></div><div class="cost">-${man(cfg.ship_cost[i])}</div><div class="road" id="road-${i}" style="display:none"><span class="truck" id="truck-${i}">🚚</span></div><button class="miniact bship" id="sh-${i}" onclick="shipFeed(${i})">배송</button>`; b.appendChild(shp);
                const frm=document.createElement('div'); frm.className='cell farm'; frm.id='frm-'+i; frm.style.gridColumn=4; frm.style.gridRow=i+2;
                frm.innerHTML=`<div class="ttl">${FARM_EMO[i]}${FARM_NAMES[i]}</div><div class="pay">+${man(cfg.sell_price[i])}</div>`; b.appendChild(frm);
            }
        }

        function buyMat(m){const p=cfg["price_"+m]; if(isBuying[m]||money<p)return; money-=p; isBuying[m]=1; buyStart[m]=performance.now(); stat.matTons[m]+=10; stat.matCost[m]+=p;}
        function makeFeed(i){if(isMaking[i])return; const rec=recipeOf(i); if(rec.some(r=>(matStocks[r.mat]||0)<r.amt))return; if(money<cfg.make_cost[i])return; money-=cfg.make_cost[i]; stat.makeCost[i]+=cfg.make_cost[i]; rec.forEach(r=>matStocks[r.mat]-=r.amt); isMaking[i]=1; makeStart[i]=performance.now();}
        function shipFeed(i){if(feedStock[i]<10||isDelivering[i]||isDisease[i])return; if(money<cfg.ship_cost[i])return; money-=cfg.ship_cost[i]; stat.shipTons[i]+=10; stat.shipCost[i]+=cfg.ship_cost[i]; feedStock[i]-=10; isDelivering[i]=1; deliverStart[i]=performance.now(); truckPos[i]=0;}

        function loop(){
            const now=performance.now(); let left=GAME_DURATION-(now-gameStartTick);
            if(left<=0){left=0; endGame(); return;}
            MAT_NAMES.forEach(m=>{if(isBuying[m]&&now-buyStart[m]>=cfg.buy_time*1000){isBuying[m]=0; matStocks[m]+=10;}});
            if(combo>0 && now-lastDeliverTick>6000) combo=0;
            for(let i=0;i<4;i++){
                if(!isDisease[i]&&Math.random()<DISEASE_CHANCE){isDisease[i]=1; diseaseStart[i]=now; diseaseLabel[i]=DISEASES[i][0];}
                if(isDisease[i]&&now-diseaseStart[i]>=DISEASE_DURATION)isDisease[i]=0;
                if(isMaking[i]&&now-makeStart[i]>=cfg.make_time[i]*1000){isMaking[i]=0; feedStock[i]+=10; stat.madeTons[i]+=10;}
                if(isDelivering[i]){
                    truckPos[i]=Math.min(1,(now-deliverStart[i])/DELIVER_TIME);
                    if(now-deliverStart[i]>=DELIVER_TIME){
                        isDelivering[i]=0; combo=(now-lastDeliverTick<=6000)?combo+1:1; lastDeliverTick=now;
                        const b=Math.min(1.0,(combo-1)*0.12); const earn=Math.round(cfg.sell_price[i]*(1+b));
                        money+=earn; stat.revenue[i]+=earn; stat.comboBonus+=(earn-cfg.sell_price[i]); toast(i,"+"+man(earn));
                    }
                }
            }
            if(!goalReached && money-cfg.start_money>=cfg.goal_profit){goalReached=true;}
            render(now,left); rafId=requestAnimationFrame(loop);
        }

        function render(now,left){
            document.getElementById('moneyText').textContent=man(money);
            const sec=Math.floor(left/1000), mm=String(Math.floor(sec/60)).padStart(2,'0'), ss=String(sec%60).padStart(2,'0');
            document.getElementById('timerText').textContent=`${mm}:${ss}`;
            const prog=Math.max(0,Math.min(1,(money-cfg.start_money)/cfg.goal_profit)); document.getElementById('goalBar').style.width=(prog*100)+'%';
            
            MAT_NAMES.forEach(m=>{
                document.getElementById('stk-'+m).textContent=matStocks[m]+'t';
                const btn=document.getElementById('buy-'+m); btn.disabled=(money<cfg['price_'+m] || isBuying[m]);
                btn.textContent=isBuying[m]?'수입중':'구매';
            });
            for(let i=0;i<4;i++){
                const rec=recipeOf(i), hasMat=rec.every(r=>(matStocks[r.mat]||0)>=r.amt), mk=document.getElementById('mk-'+i);
                mk.disabled=(!hasMat || money<cfg.make_cost[i] || isMaking[i]); mk.textContent=isMaking[i]?'가동중':'제조';
                
                document.getElementById('feedstk-'+i).textContent=feedStock[i]+'t';
                const sh=document.getElementById('sh-'+i);
                sh.disabled=(feedStock[i]<10 || money<cfg.ship_cost[i] || isDelivering[i] || isDisease[i]);
                sh.textContent=isDisease[i]?'통제중':'배송';
                
                document.getElementById('road-'+i).style.display=isDelivering[i]?'block':'none';
                if(isDelivering[i]) document.getElementById('truck-'+i).style.left=(truckPos[i]*80)+'%';
            }
        }

        function toast(i,text){
            const t=document.createElement('div'); t.className='toast'; t.textContent=text;
            const r=document.getElementById('frm-'+i).getBoundingClientRect();
            t.style.left=(r.left+10)+'px'; t.style.top=(r.top)+'px';
            document.getElementById('toastL').appendChild(t); setTimeout(()=>t.remove(),1000);
        }

        // ✨ 게임 종료 시 스트림릿으로 순이익 쏘기!
        function endGame(){
            cancelAnimationFrame(rafId); running=false;
            document.getElementById('finalMoney').textContent=man(money);
            const profit=money-cfg.start_money;
            document.getElementById('gradeText').textContent=`순이익 ${man(profit)}`;
            document.getElementById('reportBox').innerHTML=`<p style="text-align:center">수고하셨습니다! 결과를 스트림릿 서버로 전송합니다.</p>`;
            
            const parent = window.parent;
            const hiddenInput = parent.document.querySelector('input[aria-label="hidden_tycoon_data"]');
            
            if (hiddenInput && !sessionStorage.getItem('tycoonScoreSent')) {
                const dataObj = { name: playerName, team: teamName, profit: profit };
                let nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
                nativeInputValueSetter.call(hiddenInput, JSON.stringify(dataObj));
                hiddenInput.dispatchEvent(new Event('input', { bubbles: true }));
                
                setTimeout(() => {
                    hiddenInput.focus();
                    hiddenInput.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true }));
                    hiddenInput.blur();
                }, 100);
                sessionStorage.setItem('tycoonScoreSent', 'true');
            }
            show('overScreen');
        }
        </script>
        </body>
        </html>
        """
        
        # 게임 렌더링 영역
        components.html(game_html, height=750, scrolling=True)
        
        # [핵심] 자바스크립트가 보내는 순이익 데이터를 몰래 받아주는 투명한 박스
        js_data = st.text_input("hidden_tycoon_data", key="hidden_tycoon_data", label_visibility="collapsed")
        
        if js_data and 'tycoon_score_saved' not in st.session_state:
            try:
                data = json.loads(js_data)
                with st.spinner("📡 최종 경영 실적을 명예의 전당에 등록 중입니다..."):
                    if save_tycoon_score(data['name'], data['team'], data['profit']):
                        st.session_state.tycoon_score_saved = True
                        st.balloons()
                st.rerun()
            except Exception as e:
                pass
                
        if 'tycoon_score_saved' in st.session_state:
            st.success("✅ 실적이 성공적으로 명예의 전당에 등록되었습니다! [실시간 명예의 전당] 탭을 확인해보세요.")
            if st.button("🔄 게임 초기화 (다시 하기)"):
                del st.session_state['hidden_tycoon_data']
                del st.session_state['tycoon_score_saved']
                st.rerun()

    with tab2:
        st.subheader("🏆 밸류체인 최고 경영자 (Top 10)")
        if st.button("🔄 순위 새로고침"):
            get_tycoon_leaderboard.clear()
            st.rerun()
            
        board_data = get_tycoon_leaderboard()
        
        if not board_data:
            st.info("아직 등록된 경영 실적이 없습니다. 첫 번째 최고 경영자에 도전하세요!")
        else:
            try:
                # 순이익이 높은 순서대로 내림차순 정렬
                sorted_board = sorted(board_data, key=lambda x: int(str(x.get('순이익(원)', 0)).replace(',','')), reverse=True)
            except:
                sorted_board = board_data
                
            top3 = sorted_board[:3]
            c1, c2, c3 = st.columns(3)
            medals = [("🥇 1위", "gold"), ("🥈 2위", "silver"), ("🥉 3위", "bronze")]
            cols = [c1, c2, c3]
            
            for i in range(min(len(top3), 3)):
                profit_str = format(int(top3[i].get('순이익(원)', 0)), ',')
                with cols[i]:
                    st.markdown(f"""
                    <div style="border: 2px solid #efefef; padding: 25px 10px; border-radius: 15px; background-color: #ffffff; box-shadow: 0 4px 12px rgba(0,0,0,0.08); text-align: center; display: block; width: 100%;">
                        <div class="{medals[i][1]}" style="width: 100%; text-align: center; margin-bottom: 12px;">{medals[i][0]}</div>
                        <div style="width: 100%; text-align: center; font-size: 1.6em; font-weight: 800; color: #1e293b; margin-bottom: 4px;">{top3[i].get('이름', '-')}</div>
                        <div style="width: 100%; text-align: center; font-size: 1.0em; color: #64748b; margin-bottom: 15px; font-weight: 500;">{top3[i].get('소속팀', '-')}</div>
                        <div style="width: 100%; text-align: center; font-size: 1.5em; font-weight: bold; color: #4CAF50; background-color: #E8F5E9; border-radius: 8px; padding: 5px 0;">+{profit_str}원</div>
                    </div>
                    """, unsafe_allow_html=True)
            
            st.markdown("<br>", unsafe_allow_html=True)
            
            if len(sorted_board) > 3:
                df = pd.DataFrame(sorted_board[3:10])
                df.index = range(4, 4 + len(df))
                df.index.name = "순위"
                df = df[['이름', '소속팀', '순이익(원)', '달성일']]
                
                # 금액에 콤마 포맷 적용
                df['순이익(원)'] = df['순이익(원)'].apply(lambda x: f"{format(int(str(x).replace(',','')), ',')}원")
                
                styled_df = df.style.set_properties(**{
                    'text-align': 'center', 'font-family': 'sans-serif'
                }).set_table_styles([
                    {'selector': 'th', 'props': [('text-align', 'center'), ('background-color', '#f8f9fa')]}
                ])
                st.dataframe(styled_df, use_container_width=True)
