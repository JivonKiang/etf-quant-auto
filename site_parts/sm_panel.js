// ==================== SuperMind 模拟盘渲染 ====================
// V1 已平仓盈亏（28笔，采集自 SuperMind 成交明细，单位元）
const SM_PNL = [
  {d:'2026-10-26',code:'511010',name:'国债ETF',act:'卖出',pnl:-991.11},
  {d:'2026-10-19',code:'511010',name:'国债ETF',act:'卖出',pnl:-736.80},
  {d:'2026-10-12',code:'511010',name:'国债ETF',act:'卖出',pnl:-2277.7},
  {d:'2026-10-08',code:'511010',name:'国债ETF',act:'卖出',pnl:-2284.3},
  {d:'2026-09-28',code:'512100',name:'中证1000ETF',act:'卖出',pnl:-2956.6},
  {d:'2026-09-28',code:'518880',name:'黄金ETF',act:'卖出',pnl:-24972.7},
  {d:'2026-09-21',code:'518880',name:'黄金ETF',act:'卖出',pnl:-5988.1},
  {d:'2026-07-16',code:'512480',name:'半导体ETF',act:'卖出',pnl:-69692.7},
  {d:'2026-07-16',code:'588000',name:'科创50ETF',act:'卖出',pnl:-48642.9},
  {d:'2026-07-13',code:'588000',name:'科创50ETF',act:'卖出',pnl:139.69},
  {d:'2026-07-13',code:'515000',name:'科技ETF',act:'卖出',pnl:53064.5},
  {d:'2026-07-03',code:'512480',name:'半导体ETF',act:'卖出',pnl:248982.7},
  {d:'2026-06-29',code:'512480',name:'半导体ETF',act:'卖出',pnl:9865.12},
  {d:'2026-06-22',code:'512480',name:'半导体ETF',act:'卖出',pnl:5924.74},
  {d:'2026-06-22',code:'515000',name:'科技ETF',act:'卖出',pnl:107.36},
  {d:'2026-04-20',code:'515000',name:'科技ETF',act:'卖出',pnl:28396.0},
  {d:'2026-04-13',code:'511010',name:'国债ETF',act:'卖出',pnl:-1439.9},
  {d:'2026-04-07',code:'511010',name:'国债ETF',act:'卖出',pnl:-1170.8},
  {d:'2026-03-30',code:'511010',name:'国债ETF',act:'卖出',pnl:-2432.2},
  {d:'2026-03-23',code:'518880',name:'黄金ETF',act:'卖出',pnl:-53696.2},
  {d:'2026-03-23',code:'512100',name:'中证1000ETF',act:'卖出',pnl:-27995.1},
  {d:'2026-01-19',code:'512480',name:'半导体ETF',act:'卖出',pnl:1514.14},
  {d:'2026-01-12',code:'512480',name:'半导体ETF',act:'卖出',pnl:536.34},
  {d:'2026-01-05',code:'518880',name:'黄金ETF',act:'卖出',pnl:13222.3},
  {d:'2026-01-05',code:'515000',name:'科技ETF',act:'卖出',pnl:168.68},
  {d:'2025-12-29',code:'518880',name:'黄金ETF',act:'卖出',pnl:23489.6},
  {d:'2025-12-22',code:'515000',name:'科技ETF',act:'卖出',pnl:-534.83},
  {d:'2025-12-15',code:'518880',name:'黄金ETF',act:'卖出',pnl:335.70}
];
// V1 最近24笔成交（买卖流水，含建仓）
const SM_TRADES = [
  {d:'2026-10-26',code:'511010',name:'国债ETF',act:'买入',price:'141.300',vol:'+7,600',amt:'1,073,881'},
  {d:'2026-10-26',code:'511010',name:'国债ETF',act:'卖出',price:'141.018',vol:'-7,600',amt:'-1,071,736',pnl:-991.11},
  {d:'2026-10-19',code:'511010',name:'国债ETF',act:'买入',price:'141.113',vol:'+7,600',amt:'1,072,459'},
  {d:'2026-10-19',code:'511010',name:'国债ETF',act:'卖出',price:'140.831',vol:'-7,600',amt:'-1,070,316',pnl:-736.80},
  {d:'2026-10-12',code:'511010',name:'国债ETF',act:'买入',price:'140.893',vol:'+7,600',amt:'1,070,785'},
  {d:'2026-10-12',code:'511010',name:'国债ETF',act:'卖出',price:'140.611',vol:'-7,600',amt:'-1,068,645',pnl:-2277.7},
  {d:'2026-10-08',code:'511010',name:'国债ETF',act:'买入',price:'140.876',vol:'+7,600',amt:'1,070,656'},
  {d:'2026-10-08',code:'511010',name:'国债ETF',act:'卖出',price:'140.594',vol:'-7,700',amt:'-1,082,576',pnl:-2284.3},
  {d:'2026-09-28',code:'512100',name:'中证1000ETF',act:'卖出',price:'3.072',vol:'-38,900',amt:'-119,498',pnl:-2956.6},
  {d:'2026-09-28',code:'518880',name:'黄金ETF',act:'卖出',price:'8.662',vol:'-61,700',amt:'-534,466',pnl:-24972.7},
  {d:'2026-09-28',code:'511010',name:'国债ETF',act:'买入',price:'140.856',vol:'+7,700',amt:'1,084,589'},
  {d:'2026-09-21',code:'518880',name:'黄金ETF',act:'卖出',price:'8.970',vol:'-61,700',amt:'-553,450',pnl:-5988.1},
  {d:'2026-07-16',code:'512480',name:'半导体ETF',act:'卖出',price:'1.190',vol:'-491,300',amt:'-584,553',pnl:-69692.7},
  {d:'2026-07-16',code:'588000',name:'科创50ETF',act:'卖出',price:'1.975',vol:'-302,800',amt:'-598,037',pnl:-48642.9},
  {d:'2026-07-13',code:'512480',name:'半导体ETF',act:'买入',price:'1.331',vol:'+491,300',amt:'654,082'},
  {d:'2026-07-06',code:'588000',name:'科创50ETF',act:'买入',price:'2.135',vol:'+309,100',amt:'659,970'},
  {d:'2026-07-03',code:'512480',name:'半导体ETF',act:'卖出',price:'1.321',vol:'-496,400',amt:'-655,585',pnl:248982.7},
  {d:'2026-04-20',code:'515000',name:'科技ETF',act:'卖出',price:'1.127',vol:'-426,700',amt:'-480,836',pnl:28396.0},
  {d:'2026-04-13',code:'515000',name:'科技ETF',act:'买入',price:'1.060',vol:'+848,700',amt:'899,672'},
  {d:'2026-01-05',code:'518880',name:'黄金ETF',act:'卖出',price:'9.412',vol:'-46,700',amt:'-439,521',pnl:13222.3},
  {d:'2025-12-29',code:'518880',name:'黄金ETF',act:'卖出',price:'9.630',vol:'-46,800',amt:'-450,701',pnl:23489.6},
  {d:'2025-12-22',code:'518880',name:'黄金ETF',act:'买入',price:'9.389',vol:'+46,400',amt:'435,667'},
  {d:'2025-11-10',code:'518880',name:'黄金ETF',act:'买入',price:'8.878',vol:'+50,600',amt:'449,220'},
  {d:'2025-11-08',code:'—',name:'回测建仓',act:'—',price:'—',vol:'—',amt:'初始资金 ¥1,000,000'}
];
(function renderSmPnl(){
  const el = document.getElementById('smPnlChart'); if(!el) return;
  const data = SM_PNL.slice().reverse(); // 时间正序
  const W=880, H=300, padL=70, padR=16, padT=16, padB=40;
  const max=Math.max(...data.map(x=>x.pnl)), min=Math.min(...data.map(x=>x.pnl));
  const iw=W-padL-padR, ih=H-padT-padB;
  const y=v=>padT+ih*(1-(v-min)/(max-min));
  const bw=Math.max(6,iw/data.length*0.62);
  const zero=y(0);
  let s='<svg class="ps-svg" viewBox="0 0 '+W+' '+H+'" xmlns="http://www.w3.org/2000/svg">';
  s+='<line x1="'+padL+'" y1="'+zero+'" x2="'+(W-padR)+'" y2="'+zero+'" stroke="#cbd5e1" stroke-width="1"/>';
  // 网格与刻度
  [200000,100000,0,-100000].forEach(v=>{
    if(v>=min&&v<=max){ s+='<line x1="'+padL+'" y1="'+y(v)+'" x2="'+(W-padR)+'" y2="'+y(v)+'" stroke="#f1f5f9" stroke-width="1"/>';
      s+='<text x="'+(padL-8)+'" y="'+(y(v)+4)+'" text-anchor="end" font-size="11" fill="#94a3b8">'+(v/10000)+'万</text>'; }
  });
  data.forEach((x,i)=>{
    const cx=padL+iw*(i+0.5)/data.length, cy=y(x.pnl);
    const h=Math.abs(zero-cy)||1, yy=x.pnl>=0?cy:zero;
    s+='<rect x="'+(cx-bw/2)+'" y="'+yy+'" width="'+bw+'" height="'+h+'" rx="2" fill="'+(x.pnl>=0?'#ef4444':'#10b981')+'" opacity="0.9"><title>'+x.d+' '+x.code+' '+x.name+' '+x.act+' '+(x.pnl>=0?'+':'')+x.pnl.toFixed(0)+'元</title></rect>';
    if(Math.abs(x.pnl)>20000){
      s+='<text x="'+cx+'" y="'+(x.pnl>=0?yy-5:yy+h+13)+'" text-anchor="middle" font-size="10" fill="'+(x.pnl>=0?'#ef4444':'#10b981')+'" font-weight="700">'+((x.pnl>=0?'+':'')+(x.pnl/10000).toFixed(1)+'万')+'</text>';
    }
  });
  // 月份刻度（每4笔）
  data.forEach((x,i)=>{ if(i%4===0){ const cx=padL+iw*(i+0.5)/data.length;
    s+='<text x="'+cx+'" y="'+(H-14)+'" text-anchor="middle" font-size="10" fill="#94a3b8">'+x.d.slice(2,7)+'</text>'; }});
  s+='<text x="'+(padL+4)+'" y="'+(padT+2)+'" font-size="12" fill="#64748b">盈/亏笔数 14 : 14 · 涨红跌绿 · 悬停看明细</text>';
  s+='</svg>';
  el.innerHTML=s;
})();
(function renderSmTrades(){
  const el=document.getElementById('smTrades'); if(!el) return;
  let h='<tr><th>日期</th><th>标的</th><th>操作</th><th>价格</th><th>数量(股)</th><th>成交额(元)</th><th>平仓盈亏(元)</th></tr>';
  SM_TRADES.forEach(t=>{
    const actCls=t.act==='买入'?'pos':(t.act==='卖出'?'neg':'');
    const pnl=t.pnl!=null?('<span class="'+(t.pnl>=0?'pos':'neg')+'">'+(t.pnl>=0?'+':'')+t.pnl.toFixed(0)+'</span>'):'—';
    h+='<tr><td>'+t.d+'</td><td>'+t.code+' '+t.name+'</td><td class="'+actCls+'">'+t.act+'</td><td>'+t.price+'</td><td>'+t.vol+'</td><td>'+t.amt+'</td><td>'+pnl+'</td></tr>';
  });
  el.innerHTML=h;
})();