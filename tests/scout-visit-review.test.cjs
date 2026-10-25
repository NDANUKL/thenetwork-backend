const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../fieldpulse/fieldpulse/doctype/fp_task_response/fp_task_response.js'),'utf8');
async function render(data){let handler,html='',buttons=[];const wrapper={html:value=>{html=value;return wrapper;},find:()=>({on:()=>{}})};
 const frappe={ui:{form:{on:(_name,definition)=>{handler=definition.refresh;}}},user:{has_role:()=>true},utils:{escape_html:value=>String(value).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;')},call:async()=>({message:data})};
 vm.runInNewContext(source,{frappe,__ :text=>text});
 await handler({is_new:()=>false,doc:{name:'response',status:'Submitted',qa_status:'Needs Review'},fields_dict:{submission_review:{$wrapper:wrapper}},add_custom_button:label=>buttons.push(label)});
 return{html,buttons};}
(async()=>{
 const base={client_request:{client_request:'Check the approved record'},arrival:{status:'Invalid GPS'},review_status:'Needs review',review_reasons:'Arrival not verified',questions:[{name:'q',question_code:'11.1',label:'Document fields',validation_json:'{}'}],answers:[],evidence:[],summary:[]};
 const exception=await render({...base,final_review:{visit_route:'arrival_exception',arrival_exception_reason:'Assigned entrance unavailable'}});
 assert.ok(exception.html.includes('questionnaire remained locked'));assert.ok(exception.html.includes('Assigned entrance unavailable'));assert.ok(!exception.html.includes('No answer recorded'));assert.deepEqual(exception.buttons,['Request rework']);
 const normal=await render({...base,arrival:{status:'Inside'},final_review:{coverage:'Yes'},answers:[{name:'a',question:'q',answer_json:'{"result":"Matches"}'}],evidence:[{name:'file',question_response:'a',evidence_type:'Photo',caption:'Automatic label',description:'<script>issue</script>',metadata_origin:'Camera',location_sampled_at:'2026-10-24 11:00:00',location_check:{status:'Inside'},gps_lat:-1.3,gps_lng:36.8,accuracy_m:5}]});
 assert.ok(normal.html.includes('GPS sampled at'));assert.ok(normal.html.includes('Camera'));assert.ok(normal.html.includes('&lt;script&gt;issue&lt;/script&gt;'));assert.ok(!normal.html.includes('<script>'));
 console.log('PASS: coordinator arrival exception stays unanswered/unapprovable; capture provenance and escaped clarification are shown.');
})().catch(error=>{console.error(error);process.exitCode=1;});
