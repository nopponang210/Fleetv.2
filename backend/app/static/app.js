document.head.insertAdjacentHTML('beforeend','<link rel="stylesheet" href="/static/dashboard-v2.css?v=2"><link rel="stylesheet" href="/static/fleetai-neon.css?v=1">');
document.querySelector('[data-page="documents"]')?.insertAdjacentHTML('beforebegin','<button class="nav" data-page="maintenance">⌘ บำรุงรักษา</button>');
const $=s=>document.querySelector(s),token=localStorage.token;
if(window.Chart){Chart.defaults.color='#86b9d8';Chart.defaults.borderColor='rgba(0,140,255,.13)';Chart.defaults.font.family="'Plus Jakarta Sans','Sarabun',sans-serif"}
let vehicles=[],charts=[],currentExpenses=[];
const categories=['น้ำมันเชื้อเพลิง','ค่าซ่อมบำรุง','ยางรถ','ประกันภัย','ภาษีรถ','พ.ร.บ.','ล้างรถ','ทางด่วน','ที่จอดรถ','ค่าปรับ','อะไหล่','แบตเตอรี่','อุปกรณ์เสริม','อื่น ๆ'];
const esc=s=>String(s??'').replace(/[&<>"']/g,x=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[x]));
function logout(){localStorage.removeItem('token');location.href='/login'}
async function api(path,opts={}){const r=await fetch('/api'+path,{...opts,headers:{Authorization:'Bearer '+token,'Content-Type':'application/json',...(opts.headers||{})}}),raw=await r.text();let data={};try{data=raw?JSON.parse(raw):{}}catch{data={detail:raw||'ระบบตอบกลับข้อมูลผิดรูปแบบ'}}if(r.status===401){logout();throw Error('Session หมดอายุ')}if(!r.ok)throw Error(data.detail||'เกิดข้อผิดพลาด');return data}
const empty=t=>`<div class="empty-state">${esc(t)}</div>`;
const form=(t,h)=>`<section class="panel"><div class="panel-head"><h2>${t}</h2></div>${h}</section>`;
const table=(heads,rows)=>`<div class="table-wrap"><table><thead><tr>${heads.map(x=>`<th>${x}</th>`).join('')}</tr></thead><tbody>${rows.length?rows.map(r=>`<tr>${r.map(x=>`<td>${x}</td>`).join('')}</tr>`).join(''):`<tr><td colspan="${heads.length}" class="empty">ยังไม่มีข้อมูล</td></tr>`}</tbody></table></div>`;
const options=()=>vehicles.map(v=>`<option value="${v.id}">${esc(v.name)} · ${esc(v.plate_number)}</option>`).join('');
const vname=id=>{const v=vehicles.find(x=>x.id===id);return v?`${esc(v.name)} · ${esc(v.plate_number)}`:`รถ #${id}`};
function destroyCharts(){charts.forEach(x=>x.destroy());charts=[]}function chart(id,config){const el=$('#'+id);if(el&&window.Chart)charts.push(new Chart(el,config))}
async function init(){try{const me=await api('/me');$('#profile').textContent=me.name;$('#role').textContent=me.role.toUpperCase();vehicles=await api('/vehicles');document.querySelectorAll('.nav').forEach(x=>x.onclick=()=>show(x.dataset.page));show('overview')}catch(e){$('#content').innerHTML=empty(e.message)}}
async function show(page){destroyCharts();document.querySelectorAll('.nav').forEach(x=>x.classList.toggle('active',x.dataset.page===page));$('#pageTitle').textContent={overview:'ภาพรวมระบบ',vehicles:'รถทั้งหมด',mileages:'บันทึกเลขไมล์',expenses:'ค่าใช้จ่าย',maintenance:'บำรุงรักษา',documents:'เอกสารรถ',line:'เชื่อมต่อ LINE'}[page];try{await ({overview,vehicles:vehiclePage,mileages:mileagePage,expenses:expensePage,maintenance,documents,line}[page])()}catch(e){$('#content').innerHTML=empty(e.message)}}
const badge=s=>`<span class="status ${s}">${s==='overdue'?'เกินกำหนด':s==='due'?'ใกล้กำหนด':'ปกติ'}</span>`;
async function overview(){const selected=localStorage.fleetVehicle||'all',d=await api('/dashboard'+(selected==='all'?'':'?vehicle_id='+selected));$('#content').innerHTML=`<div class="toolbar"><label>กรองยานพาหนะ<select id="filter"><option value="all">ทุกคันในกองรถ</option>${options()}</select></label><div class="quick-actions"><button data-go="vehicles">+ เพิ่มรถ</button><button data-go="mileages">บันทึกเลขไมล์</button><button data-go="expenses">บันทึกค่าใช้จ่าย</button></div></div><div class="kpi-grid"><article class="kpi"><span>ยานพาหนะทั้งหมด</span><strong>${d.vehicles}</strong><small>ใช้งาน ${d.active_vehicles} · หยุดใช้งาน ${d.inactive_vehicles}</small></article><article class="kpi"><span>ค่าใช้จ่ายเดือนนี้</span><strong>฿${Number(d.month_expense).toLocaleString()}</strong><small>ข้อมูลจริงจากระบบ</small></article><article class="kpi"><span>เอกสารต้องติดตาม</span><strong>${d.due_documents}</strong><small>หมดอายุหรือภายใน 30 วัน</small></article><article class="kpi"><span>บำรุงรักษา</span><strong>${d.maintenance.length}</strong><small>เกินกำหนด ${d.maintenance_overdue} รายการ</small></article></div><div class="dash-grid">${form('ค่าใช้จ่ายย้อนหลัง 6 เดือน','<div class="chart-container"><canvas id="expenseChart"></canvas></div>')}${form('แนวโน้มเลขไมล์','<div class="chart-container"><canvas id="mileageChart"></canvas></div>')}${form('ต้องจัดการวันนี้',alerts(d))}${form('รายการล่าสุด',recent(d.recent))}${form('ค่าใช้จ่ายเดือนนี้ แยกตามรถ',table(['รถ','ยอดเงิน'],d.expense_by_vehicle.map(x=>[`${esc(x.name)}<br><small>${esc(x.plate_number)}</small>`,'฿'+Number(x.amount).toLocaleString()])))}</div>`;$('#filter').value=selected;$('#filter').onchange=e=>{localStorage.fleetVehicle=e.target.value;show('overview')};document.querySelectorAll('[data-go]').forEach(x=>x.onclick=()=>show(x.dataset.go));drawCharts(d)}
function alerts(d){const rows=[...d.document_alerts,...d.maintenance];return rows.length?`<div class="alert-list">${rows.map(x=>`<div class="alert-row"><div><b>${esc(x.title)}</b><small>${esc(x.detail||x.vehicle_name+' · '+x.plate_number)}</small></div>${badge(x.state)}</div>`).join('')}</div>`:empty('ไม่มีรายการที่ต้องติดตาม')}
function recent(rows){return rows.length?`<div class="recent-list">${rows.map(x=>`<div class="recent-row"><div><b>${esc(x.title)}</b><small>${esc(x.detail)}</small></div><time>${new Date(x.at).toLocaleString('th-TH')}</time></div>`).join('')}</div>`:empty('ยังไม่มีรายการบันทึก')}
function drawCharts(d){
  const labels=d.monthly_expenses.map(x=>x.month);
  const keys=[
    ['น้ำมัน','fuel','#ff273d'],
    ['บำรุงรักษา','maintenance','#23f29a'],
    ['อะไหล่','parts','#fbbf24'],
    ['อื่น ๆ','other','#00dcff']
  ];
  chart('expenseChart',{
    type:'bar',
    data:{
      labels,
      datasets:keys.map(x=>({
        label:x[0],
        data:d.monthly_expenses.map(y=>y[x[1]]),
        backgroundColor:x[2],
        borderRadius:4
      }))
    },
    options:{
      responsive:true,
      maintainAspectRatio:false,
      plugins:{
        legend:{labels:{font:{family:"'Outfit','Sarabun',sans-serif",size:11}}},
        tooltip:{backgroundColor:'rgba(3,8,19,0.95)',borderColor:'rgba(0,220,255,0.3)',borderWidth:1,padding:10,cornerRadius:8}
      },
      scales:{
        x:{stacked:true,grid:{color:'rgba(0,220,255,0.04)'},ticks:{font:{family:"'Outfit','Sarabun',sans-serif"}}},
        y:{stacked:true,beginAtZero:true,grid:{color:'rgba(0,220,255,0.04)'},ticks:{font:{family:"'Outfit','Sarabun',sans-serif"}}}
      }
    }
  });
  const mileage=d.mileage_trend.map(x=>x.mileage);
  if(!mileage.some(x=>x>0)){
    $('#mileageChart').parentElement.innerHTML=empty('ยังไม่มีข้อมูลเลขไมล์ในช่วง 6 เดือน');
    return;
  }
  const mCanvas=$('#mileageChart');
  let mGrad=null;
  if(mCanvas){
    const ctx=mCanvas.getContext('2d');
    mGrad=ctx.createLinearGradient(0,0,0,180);
    mGrad.addColorStop(0,'rgba(0,220,255,0.22)');
    mGrad.addColorStop(1,'rgba(0,220,255,0.0)');
  }
  chart('mileageChart',{
    type:'line',
    data:{
      labels,
      datasets:[{
        label:'เลขไมล์สะสม (กม.)',
        data:mileage,
        borderColor:'#00dcff',
        backgroundColor:mGrad||'transparent',
        fill:true,
        tension:.35,
        borderWidth:3,
        pointBackgroundColor:'#23f29a',
        pointBorderColor:'#fff',
        pointRadius:4,
        pointHoverRadius:6
      }]
    },
    options:{
      responsive:true,
      maintainAspectRatio:false,
      plugins:{
        legend:{labels:{font:{family:"'Outfit','Sarabun',sans-serif",size:11}}},
        tooltip:{backgroundColor:'rgba(3,8,19,0.95)',borderColor:'rgba(0,220,255,0.3)',borderWidth:1,padding:10,cornerRadius:8}
      },
      scales:{
        x:{grid:{color:'rgba(0,220,255,0.04)'},ticks:{font:{family:"'Outfit','Sarabun',sans-serif"}}},
        y:{grid:{color:'rgba(0,220,255,0.04)'},ticks:{font:{family:"'Outfit','Sarabun',sans-serif"}}}
      }
    }
  });
}
async function vehiclePage(){$('#content').innerHTML=`<div class="two-col">${form('เพิ่มรถใหม่',`<form id="vehicleForm" class="grid-form"><label>ชื่อรถ<input name="name" required></label><label>ทะเบียน<input name="plate_number" required></label><label>ประเภท<select name="vehicle_type"><option value="car">รถยนต์</option><option value="motorcycle">รถจักรยานยนต์</option></select></label><button>เพิ่มรถ</button></form>`)}${form('รถทั้งหมด',table(['ชื่อรถ','ทะเบียน','ประเภท','เลขไมล์ปัจจุบัน'],vehicles.map(v=>[esc(v.name),esc(v.plate_number),v.vehicle_type==='car'?'รถยนต์':'รถจักรยานยนต์',Number(v.current_mileage).toLocaleString()+' กม.'])))}</div>`;$('#vehicleForm').onsubmit=e=>submit(e,'/vehicles',true)}
async function mileagePage(){
  const rows=await api('/mileages');
  $('#content').innerHTML=`<div class="two-col">
    ${form('บันทึกเลขไมล์',`<form id="mileageForm" class="grid-form"><label>รถ<select name="vehicle_id">${options()}</select></label><label>เลขไมล์<input type="number" min="0" name="mileage" required></label><label>หมายเหตุ<input name="note"></label><button>บันทึกเลขไมล์</button></form>`)}
    ${form('ประวัติเลขไมล์',table(['รถ','เลขไมล์','หมายเหตุ','สถานะ','เวลา','ดำเนินการ'],rows.map(x=>[
      vname(x.vehicle_id),
      Number(x.mileage).toLocaleString()+' กม.',
      esc(x.note || ''),
      esc(x.ocr_status),
      new Date(x.recorded_at).toLocaleString('th-TH'),
      `<button class="small-action danger" onclick="remove('mileages',${x.id},'mileages')" style="background:var(--neon-red);color:#fff;border-color:var(--neon-red)">ลบ</button>`
    ])))}
  </div>`;
  $('#mileageForm').onsubmit=e=>submit(e,'/mileages');
}
async function expensePage(){
  const rows=await api('/expenses');
  currentExpenses=rows;
  $('#content').innerHTML=`<div class="two-col">
    ${form('บันทึกค่าใช้จ่าย',`<form id="expenseForm" class="grid-form"><label>รถ<select name="vehicle_id">${options()}</select></label><label>หมวด<select name="category">${categories.map(x=>`<option>${x}</option>`).join('')}</select></label><label>จำนวนเงิน<input type="number" min="0" step=".01" name="amount" required></label><label>วันที่<input type="date" name="expense_date" value="${new Date().toISOString().slice(0,10)}"></label><label>อู่/ร้านค้า<input name="garage_name"></label><label>หมายเหตุ<input name="note"></label><button>บันทึกค่าใช้จ่าย</button></form>`)}
    ${form('ประวัติค่าใช้จ่าย',table(['รถ','หมวด','รายละเอียด','จำนวนเงิน','วันที่','ดำเนินการ'],rows.map(x=>[
      vname(x.vehicle_id),
      esc(x.category),
      esc(x.note || ''),
      '฿'+Number(x.amount).toLocaleString(),
      esc(x.expense_date),
      `<div style="display:flex;gap:4px">
        <button class="small-action" onclick="editExpense(${x.id})">แก้ไข</button>
        <button class="small-action danger" onclick="remove('expenses',${x.id},'expenses')" style="background:var(--neon-red);color:#fff;border-color:var(--neon-red)">ลบ</button>
      </div>`
    ])))}
  </div>`;
  $('#expenseForm').onsubmit=e=>submit(e,'/expenses');
}
async function maintenance(){const rows=await api('/maintenance-schedules'),tableRows=rows.map(x=>[`${esc(x.vehicle_name)}<br><small>${esc(x.plate_number)}</small>`,esc(x.title),`${x.due_mileage?Number(x.due_mileage).toLocaleString()+' กม. ':''}${x.due_date||''}`||'-',badge(x.state),`<button class="small-action" data-complete="${x.id}" data-mileage="${x.current_mileage}">บันทึกเสร็จ</button>`]);$('#content').innerHTML=`<div class="two-col">${form('ตั้งรอบบำรุงรักษา',`<form id="scheduleForm" class="grid-form"><label>รถ<select name="vehicle_id">${options()}</select></label><label>รายการ<input name="title" required placeholder="เช่น เปลี่ยนน้ำมันเครื่อง"></label><label>ทุกกี่กิโลเมตร<input type="number" min="1" name="interval_km"></label><label>ทุกกี่วัน<input type="number" min="1" name="interval_days"></label><label>เลขไมล์ที่ทำล่าสุด<input type="number" min="0" name="last_performed_mileage"></label><label>วันที่ทำล่าสุด<input type="date" name="last_performed_date"></label><button>บันทึกรอบ</button></form>`)}${form('รายการบำรุงรักษา',table(['รถ','รายการ','กำหนดถัดไป','สถานะ','ดำเนินการ'],tableRows))}</div>`;$('#scheduleForm').onsubmit=e=>submit(e,'/maintenance-schedules');document.querySelectorAll('[data-complete]').forEach(b=>b.onclick=()=>completeMaintenance(b.dataset.complete,b.dataset.mileage))}
async function documents(){const rows=await api('/documents');$('#content').innerHTML=`<div class="two-col">${form('เพิ่มเอกสารรถ',`<form id="documentForm" class="grid-form"><label>รถ<select name="vehicle_id">${options()}</select></label><label>ประเภท<select name="document_type"><option value="compulsory_insurance">พ.ร.บ.</option><option value="tax">ภาษีรถ</option><option value="insurance">ประกันภัย</option><option value="registration">ทะเบียนรถ</option></select></label><label>วันหมดอายุ<input type="date" name="expiry_date" required></label><button>บันทึกเอกสาร</button></form>`)}${form('เอกสารรถ',table(['รถ','ประเภท','หมดอายุ'],rows.map(x=>[vname(x.vehicle_id),esc(x.document_type),esc(x.expiry_date)])))}</div>`;$('#documentForm').onsubmit=e=>submit(e,'/documents')}
async function line(){
  $('#content').innerHTML=form('เชื่อมต่อ LINE Bot',`
    <div class="grid-form" style="max-width:500px;margin:0 auto">
      <label>เลือกยานพาหนะที่จะผูกกับ LINE *
        <select id="lineVehicle">${options()}</select>
      </label>
      <button id="btnGenPair" style="margin-top:10px">สร้างรหัสยืนยัน <span>⚡</span></button>
    </div>
    <div id="pairResult" style="margin-top:24px;max-width:500px;margin-left:auto;margin-right:auto" hidden></div>
  `);
  $('#btnGenPair').onclick=async()=>{
    const vid=$('#lineVehicle').value;
    if(!vid)return alert('กรุณาเลือกยานพาหนะ');
    try{
      const r=await api(`/line/pair-code/${vid}`,{method:'POST'});
      const resEl=$('#pairResult');
      resEl.hidden=false;
      resEl.innerHTML=`
        <div class="card" style="text-align:center;padding:24px;background:rgba(11,19,34,0.6);border:1px solid var(--border-hover);border-radius:16px;box-shadow:var(--glow-shadow)">
          <h3 style="color:var(--accent-cyan);margin-bottom:12px;font-size:18px">รหัสผูกบัญชีสำเร็จ!</h3>
          <strong style="font-size:36px;letter-spacing:6px;color:#fff;display:block;margin:12px 0">${esc(r.code)}</strong>
          <p style="margin:14px 0 8px 0;font-size:14px;color:var(--text-primary)">ส่งคำสั่งในแชต LINE บอท:</p>
          <code style="display:inline-block;padding:8px 16px;background:#050a12;border:1px solid var(--border-color);border-radius:8px;font-size:16px;color:var(--accent-mint);font-family:monospace;font-weight:bold">${esc(r.instruction.replace('ส่งข้อความ LINE: ',''))}</code>
          <p style="margin-top:14px;font-size:12px;color:var(--text-muted)">รหัสใช้งานได้ครั้งเดียวและมีอายุ 10 นาที</p>
        </div>
      `;
    }catch(err){
      alert(err.message);
    }
  };
}
async function submit(e,path,refreshVehicles=false){
  e.preventDefault();
  try{
    const data=Object.fromEntries(new FormData(e.target));
    ['vehicle_id','mileage','amount','interval_km','interval_days','last_performed_mileage'].forEach(k=>{
      if(data[k])data[k]=Number(data[k]);
      else if(['interval_km','interval_days','last_performed_mileage'].includes(k))data[k]=null;
    });
    const id=e.target.dataset.id;
    if(id){
      await api(path+'/'+id,{method:'PATCH',body:JSON.stringify(data)});
      delete e.target.dataset.id;
    }else{
      await api(path,{method:'POST',body:JSON.stringify(data)});
    }
    if(refreshVehicles)vehicles=await api('/vehicles');
    show(document.querySelector('.nav.active').dataset.page);
  }catch(err){
    alert(err.message);
  }
}
window.remove=async(type,id,page)=>{
  if(!confirm('ยืนยันลบรายการนี้หรือไม่? การดำเนินการนี้ย้อนกลับไม่ได้'))return;
  try{
    await api(`/${type}/${id}`,{method:'DELETE'});
    alert('ลบข้อมูลเรียบร้อย');
    show(page);
  }catch(err){
    alert(err.message);
  }
};
window.editExpense=(id)=>{
  const x=currentExpenses.find(item=>item.id===id);
  if(!x)return;
  const formEl=$('#expenseForm');
  if(formEl){
    formEl.dataset.id=x.id;
    formEl.querySelector('[name="vehicle_id"]').value=x.vehicle_id;
    formEl.querySelector('[name="category"]').value=x.category;
    formEl.querySelector('[name="amount"]').value=x.amount;
    formEl.querySelector('[name="expense_date"]').value=x.expense_date;
    formEl.querySelector('[name="garage_name"]').value=x.garage_name||'';
    formEl.querySelector('[name="note"]').value=x.note||'';
    formEl.querySelector('button').textContent='บันทึกการแก้ไข';
    if(!formEl.querySelector('#btnCancelEdit')){
      formEl.insertAdjacentHTML('beforeend','<button type="button" id="btnCancelEdit" class="secondary" style="background:#55758d;color:#fff;margin-top:10px;width:100%">ยกเลิกแก้ไข</button>');
      formEl.querySelector('#btnCancelEdit').onclick=()=>{
        formEl.reset();
        delete formEl.dataset.id;
        formEl.querySelector('button').textContent='บันทึกค่าใช้จ่าย';
        formEl.querySelector('#btnCancelEdit').remove();
      };
    }
  }
};
async function completeMaintenance(id,currentMileage){const mileage=prompt('เลขไมล์ขณะเข้ารับบริการ',currentMileage),performedDate=prompt('วันที่ดำเนินการ (YYYY-MM-DD)',new Date().toISOString().slice(0,10));if(mileage===null||performedDate===null)return;try{await api(`/maintenance-schedules/${id}/complete`,{method:'POST',body:JSON.stringify({mileage:Number(mileage),performed_date:performedDate})});show('maintenance')}catch(err){alert(err.message)}}
init();
