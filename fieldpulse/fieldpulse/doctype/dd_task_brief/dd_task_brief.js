frappe.ui.form.on('DD Task Brief', {
  refresh(frm) {
    if (frm.doc.status !== 'Approved') {
      frm.add_custom_button(__('Edit Task Brief'), () => editTaskBrief(frm));
      if (!frm.is_new()) frm.add_custom_button(__('Approve Task Brief'), async () => {
        const previous = frm.doc.status;
        try {
          await frm.set_value('status', 'Approved');
          await frm.save();
        } catch (error) {
          await frm.set_value('status', previous);
          frm.enable_save();
          throw error;
        }
      });
    }
    if (frm.doc.status === 'Approved') {
      frm.disable_save();
      frm.add_custom_button(__('Create revised draft'), async () => {
        const result = await frappe.call({
          method: 'fieldpulse.fieldpulse.doctype.dd_task_brief.dd_task_brief.revise',
          args: {brief: frm.doc.name}, freeze: true,
        });
        frappe.set_route('Form', 'DD Task Brief', result.message);
      });
    }
  },
});

function editTaskBrief(frm) {
  let content;
  try {content = JSON.parse(frm.doc.content_json || '{}');}
  catch {frappe.msgprint(__('The draft JSON could not be read.'));return;}
  const dialog = new frappe.ui.Dialog({title:__('Review Task Brief'),size:'extra-large',fields:[
    {fieldname:'title',label:__('Task title'),fieldtype:'Data',reqd:1,default:content.title},
    {fieldname:'category',label:__('Category'),fieldtype:'Select',options:[
      {label:'Land and Property',value:'land_property_check'}, {label:'Construction Progress',value:'construction_progress'},
      {label:'Business and Asset',value:'business_asset_check'}, {label:'Custom Ground Verification',value:'custom_ground_verification'}],default:content.category,reqd:1},
    ...['objective','scope'].map(key=>({fieldname:key,label:__(frappe.utils.to_title_case(key)),fieldtype:'Small Text',reqd:1,default:content[key]})),
    ...['deliverables','instructions','review_reasons'].map(key=>({fieldname:key,label:__(key.replaceAll('_',' ')+' (one per line)'),fieldtype:'Small Text',default:(content[key]||[]).join('\n')})),
    {fieldname:'checks',label:__('Field checks — drag rows to reorder'),fieldtype:'Table',in_place_edit:true,
      description:__('Photo and video captures use “What to observe or document” unless a separate capture instruction is supplied.'),
      data:(content.checks||[]).map(check=>({id:check.id,instruction:check.instruction,response_type:check.response_type,required:check.required,
        options:check.options.join('\n'),photos:check.evidence.find(r=>r.kind==='photo')?.minimum||0,
        photo_instruction:check.evidence.find(r=>r.kind==='photo')?.instruction||'',videos:check.evidence.find(r=>r.kind==='video')?.minimum||0,
        video_instruction:check.evidence.find(r=>r.kind==='video')?.instruction||''})),
      fields:[{fieldname:'id',label:__('Check ID'),fieldtype:'Data',read_only:1},
        {fieldname:'instruction',label:__('What to observe or document'),fieldtype:'Small Text',reqd:1,in_list_view:1,columns:4},
        {fieldname:'response_type',label:__('Response'),fieldtype:'Select',options:'text\nsingle\nmultiple\nnone',default:'text',in_list_view:1,reqd:1},
        {fieldname:'required',label:__('Required'),fieldtype:'Check',default:1,in_list_view:1},
        {fieldname:'options',label:__('Selection choices (one per line)'),fieldtype:'Small Text'},
        {fieldname:'photos',label:__('Photos (minimum)'),fieldtype:'Int',default:0,in_list_view:1,columns:1},
        {fieldname:'photo_instruction',label:__('What the photographs should show'),fieldtype:'Small Text'},
        {fieldname:'videos',label:__('Videos (minimum)'),fieldtype:'Int',default:0,in_list_view:1,columns:1},
        {fieldname:'video_instruction',label:__('What the videos should show'),fieldtype:'Small Text'}]},
  ],primary_action_label:__('Save draft changes'),async primary_action(values){
    const lines=value=>(value||'').split('\n').map(v=>v.trim()).filter(Boolean);
    const reasons=lines(values.review_reasons);
    content={schema_version:1,category:values.category,title:values.title,objective:values.objective,scope:values.scope,
      deliverables:lines(values.deliverables),instructions:lines(values.instructions),review_required:!!reasons.length,review_reasons:reasons,
      checks:(values.checks||[]).map(row=>({id:row.id||crypto.randomUUID(),instruction:row.instruction,response_type:row.response_type,
        required:!!row.required,options:lines(row.options),evidence:[
          ...(row.photos>0?[{kind:'photo',minimum:row.photos,instruction:captureInstruction(row.photo_instruction,row.instruction)}]:[]),
          ...(row.videos>0?[{kind:'video',minimum:row.videos,instruction:captureInstruction(row.video_instruction,row.instruction)}]:[])]}))};
    await frm.set_value('content_json',JSON.stringify(content,null,2));
    await frm.save();dialog.hide();
  }});
  dialog.show();
}

function captureInstruction(specific, instruction) {
  const value = (specific || '').trim() || (instruction || '').trim();
  if (!value || value.length > 1000) {
    frappe.throw(__('For a check requiring photos or videos, enter an instruction of 1 to 1000 characters in “What to observe or document”.'));
  }
  return value;
}
