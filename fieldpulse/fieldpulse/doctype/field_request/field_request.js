if (frappe.boot.dd_native_handover_active) {
// DD Alignment Project Form
frappe.ui.form.on("Field Request", {
  refresh(frm) {
    frm.set_df_property("source", "read_only", 1);
    frm.set_df_property("diaspora_request", "hidden", !frm.doc.diaspora_request);
    if (!frm.doc.diaspora_request) {
      if (frm.doc.source !== "Manual") frm.set_value("source", "Manual");
      return;
    }
    ["source", "source_reference", "diaspora_request", "request_type", "county", "field_brief", "project_number", "project_title", "project_key", "evidence_requirements", "customer_target_date", "deadline_preference", "status"].forEach(field => frm.set_df_property(field, "read_only", 1));
    frm.set_df_property("source_reference", "hidden", 1);
    frm.set_df_property("dd_site_locations", "hidden", 1);
    frm.set_df_property("deadline", "label", "Agreed work deadline");
    frm.set_df_property("deadline", "description", "Copied to the scout task's Due date. Confirm this date when arranging the work.");
    const missing = [];
    if (!frm.doc.county) missing.push("Add the project county.");
    if (!frm.doc.evidence_requirements) missing.push("Confirm the project's evidence requirements.");
    if (frm.doc.alignment_review && !missing.length) missing.push("Review the agreed brief and tick Checklist reviewed before assigning a scout.");
    frm.set_intro(missing.join(" "), "orange");
  },
});


// DD Project Scout Assignment
frappe.ui.form.on("Field Request", {
  refresh(frm) {
    frm.remove_custom_button(__("Assign scouts"));
    frm.set_df_property("priority", "description", "");
    frm.set_df_property("deadline", "description", "");
    frm.set_df_property("status", "description", __("Use Assign scouts to select a Scout Profile and create their Field Task. Changing status alone does not assign a scout."));

    if (frm.is_new() || ["Completed", "Cancelled"].includes(frm.doc.status) || !frm.perm.some(p => p.write)) return;
    frm.add_custom_button(__("Assign scouts"), () => {
      if (frm.is_dirty()) {
        frappe.msgprint(__("Save this project before assigning scouts."));
        return;
      }
      if ((frm.doc.diaspora_request && !frm.doc.project_number) || frm.doc.alignment_review || !frm.doc.county) {
        frappe.msgprint(__("Confirm this project's scope, project number and county before assigning scouts."));
        return;
      }
      const dialog = new frappe.ui.Dialog({
        title: __("Assign scouts to this project"),
        fields: [{ fieldname: "assignment_help", fieldtype: "HTML", options: `<p>${__("Choose a scout in the row below. Use Add Row for more scouts.")}</p>` },
          { fieldname: "assignments", label: __("Scout assignments"), fieldtype: "Table", reqd: 1, in_place_edit: true, data: [{}],
          fields: [
            { fieldname: "scout", label: __("Scout"), fieldtype: "Link", options: "Scout Profile", reqd: 1, in_list_view: 1,
              get_query: () => ({ filters: { access_status: ["!=", "Deactivated"] } }),
              async onchange() {
                const row = this.doc;
                if (!row) return;
                const selected = row.scout;
                row.scout_name = "";
                row.base_county = "";
                dialog.fields_dict.assignments.grid.refresh();
                if (!selected) return;
                const result = await frappe.db.get_value("Scout Profile", selected, ["scout_name", "base_county"]);
                if (row.scout !== selected) return;
                row.scout_name = result.message?.scout_name || "";
                row.base_county = result.message?.base_county || __("County unconfirmed");
                dialog.fields_dict.assignments.grid.refresh();
              },
            },
            { fieldname: "scout_name", label: __("Full name"), fieldtype: "Data", read_only: 1, in_list_view: 1 },
            { fieldname: "base_county", label: __("County"), fieldtype: "Data", read_only: 1, in_list_view: 1 },
            { fieldname: "questionnaire", label: __("Questionnaire"), fieldtype: "Link", options: "FP Questionnaire",
              get_query: () => ({filters: frm.doc.scout_questionnaire ? {name:frm.doc.scout_questionnaire} : {status:"Published",title:["not like","%University fee payment confirmation%"],project:["is","not set"]}}) },
          ] }],
        primary_action_label: __("Assign"),
        async primary_action(values) {
          dialog.disable_primary_action();
          try {
            const result = await frappe.call({ method: "dd_assign_scouts_without_extra_columns", args: { field_request: frm.doc.name, assignments: JSON.stringify(values.assignments) }, freeze: true });
            dialog.hide();
            const assigned = await frappe.db.get_list("Field Task", {filters: {name: ["in", result.message.tasks]}, fields: ["name", "task_number"], limit: 20});
            frappe.msgprint(__("Scout tasks: {0}", [assigned.map(task => task.task_number || task.name).join(", ")]));
            await frm.reload_doc();
          } finally { dialog.enable_primary_action(); }
        },
      });
      dialog.show();
    });
  },
});


}

frappe.ui.form.on("Field Request", {
  setup(frm) {
    frm.set_query("question", "scout_checks", () => ({filters: {questionnaire: frm.doc.scout_questionnaire, active: 1, question_group: "Service"}}));
  },
  scout_service(frm) {
    if (!frm.doc.scout_service) return;
    frm.set_value("scout_questionnaire", null);
    frm.clear_table("scout_checks");
    frm.set_value("scout_checks_confirmed", 0);
    frm.refresh_field("scout_checks");
    frm.set_intro(__("Save to load this service template, then review its selected checks before confirming dispatch."));
  }
});

function scoutConfigurationFields(template) {
  const mediaOptions = ['No media', 'Photo', 'Video', 'Photo and video', 'Document'];

  const fields = [
    {fieldname:'configuration_help',fieldtype:'HTML',options:'<p>'+frappe.utils.escape_html((template.evidence||[]).map(r=>r.kind+': '+r.subject).join('; ') || 'This question needs no attachment unless you add an evidence requirement.')+'</p>'},
    {fieldname:'enabled',fieldtype:'Check',label:__('Include this assigned conditional check'),default:1,hidden:!template.assigned_only},
    {fieldname:'items',fieldtype:'Table',in_place_edit:true,label:__('Specific items or questions for this visit'),hidden:!['checklist','interview','custom'].includes(template.answer_type),fields:[
      {fieldname:'id',fieldtype:'Data',hidden:1},
      {fieldname:'label',fieldtype:'Small Text',label:__('What should the scout check or ask?'),reqd:1,in_list_view:1},
      {fieldname:'reference',fieldtype:'Small Text',label:__('Supplied reference / expected detail')},
      {fieldname:'quantity_required',fieldtype:'Check',label:__('Record quantity')},
      {fieldname:'reading_required',fieldtype:'Check',label:__('Record assigned reading')},
      {fieldname:'not_applicable_permitted',fieldtype:'Check',label:__('Allow Not applicable for this custom question')},
      {fieldname:'demonstration_required',fieldtype:'Check',label:__('Function demonstration assigned')},
      {fieldname:'video_demonstration_required',fieldtype:'Check',label:__('Video demonstration required')},
      {fieldname:'media',fieldtype:'Select',label:__('Custom question evidence'),hidden:template.answer_type!=='custom',options:mediaOptions.join('\n'),default:'No media'},
      {fieldname:'subject',fieldtype:'Small Text',label:__('Subject to capture for custom question'),hidden:template.answer_type!=='custom'},
      {fieldname:'when',fieldtype:'Small Text',label:__('Required for these answers only (separate with |)'),hidden:template.answer_type!=='custom'},
    ]},
    {fieldname:'confirmation_method',fieldtype:'Select',label:__('Permitted confirmation method'),options:'\nVerbal\nWritten\nAuthorised photo',reqd:!!template.confirmation,hidden:!template.confirmation},
    {fieldname:'confirmation_subject',fieldtype:'Small Text',label:__('What document or information may the scout collect?'),hidden:!template.confirmation,depends_on:"eval:doc.confirmation_method && doc.confirmation_method !== 'Verbal'",mandatory_depends_on:"eval:doc.confirmation_method && doc.confirmation_method !== 'Verbal'"},
    {fieldname:'physical_inspection',fieldtype:'Check',label:__('Inspect physical document (otherwise compare supplied files)'),hidden:!template.inspection},
    {fieldname:'walkthrough_subject',fieldtype:'Small Text',label:__('Assigned walkthrough: areas to record in one video'),hidden:!template.walkthrough},
    {fieldname:'delivery_document_subject',fieldtype:'Small Text',label:__('Delivery document fields to photograph, if assigned'),hidden:!template.delivery_document},
    {fieldname:'verification_subject',fieldtype:'Small Text',label:__('Optional: products, facilities or signs to photograph'),hidden:!template.optional_verification},
    {fieldname:'extra_capture',fieldtype:'Check',label:__('Add extra attachment requirements')},
    {fieldname:'additional_evidence',fieldtype:'Table',in_place_edit:true,depends_on:'eval:doc.extra_capture',label:__('Optional extra photos, videos or documents'),fields:[
      {fieldname:'id',fieldtype:'Data',hidden:1},
      {fieldname:'media',fieldtype:'Select',label:__('Media'),options:mediaOptions.slice(1).join('\n'),reqd:1,in_list_view:1},
      {fieldname:'subject',fieldtype:'Small Text',label:__('Exact subject to capture'),reqd:1,in_list_view:1},
      {fieldname:'when',fieldtype:'Small Text',label:__('Only for these answers (separate with |)')},
    ]},
  ];
  return fields;
}

function scoutConfiguration(values, template) {
  const config = {};
  for (const key of ['enabled','confirmation_method','confirmation_subject','physical_inspection','walkthrough_subject','delivery_document_subject','verification_subject']) if (values[key] !== undefined && values[key] !== '') config[key]=values[key];
  const rules=(media,subject,when,id)=>!media || media==='No media'?[]:(media==='Photo and video'?['Photo','Video']:[media]).map(kind=>({id:id+'-'+kind.toLowerCase(),kind,subject,...(when?{when:when.split('|').map(v=>v.trim()).filter(Boolean)}:{})}));
  if (['checklist','interview','custom'].includes(template.answer_type)) config.items=(values.items||[]).map(item=>({...item,id:item.id||scoutInternalId(),...(template.answer_type==='custom'?{evidence:rules(item.media,item.subject,item.when,'custom')}:{})}));
  config.additional_evidence=(values.extra_capture?values.additional_evidence||[]:[]).flatMap(item=>rules(item.media,item.subject,item.when,item.id||scoutInternalId()));
  return config;
}

function scoutInternalId() { return 'entry-'+crypto.randomUUID(); }

// Applied to the native Field Request asset. Edits belong to these child rows only.
frappe.ui.form.on('Field Request', {
  refresh(frm) {
    for (const field of ['customer_coverage_section','customer_scope_reference','customer_scope_version','customer_checks','customer_checks_confirmed','customer_checks_reviewed_by','customer_checks_reviewed_at']) frm.set_df_property(field,'hidden',1);
    frm.set_df_property('scout_checks','description',__('Review the questions below. Use Edit question and evidence in a row to change its wording, items or attachments. Save your edits, then tick Checklist reviewed, save and use Assign scouts.'));

  }
});

frappe.ui.form.on('DD Scout Check', {
  label(frm) {frm.set_value('scout_checks_confirmed',0);},
  instructions(frm) {frm.set_value('scout_checks_confirmed',0);},
  scout_checks_add(frm) {frm.set_value('scout_checks_confirmed',0);},
  scout_checks_remove(frm) {frm.set_value('scout_checks_confirmed',0);},
  scout_checks_move(frm) {frm.set_value('scout_checks_confirmed',0);},
  async question(frm,cdt,cdn) {
    const row=locals[cdt][cdn];
    if (row.question) {
      const {message}=await frappe.db.get_value('FP Question',row.question,['label']);
      await frappe.model.set_value(cdt,cdn,'label',message.label);
    }
    await frappe.model.set_value(cdt,cdn,'answer_format',row.question?'Template format':'Written answer');
    await frm.set_value('scout_checks_confirmed',0);
  },
  async edit_question(frm,cdt,cdn) {
    const row=locals[cdt][cdn];
    if (frm.is_new()) {frappe.msgprint(__('Save the project and load its template first.'));return;}
    let settings={template:false,evidence:[],options:[],protected:false};
    if (row.question) ({message:settings}=await frappe.call('fieldpulse.scout_v2.question_editor_settings',{project:frm.doc.name,question:row.question,configuration:row.configuration_json}));
    const template=settings.configuration_template||{};
    const saved=JSON.parse(row.configuration_json||'{}');
    let rules;
    try {rules=row.evidence_mode==='Specify evidence'?JSON.parse(row.evidence_json||'[]'):settings.evidence;} catch {rules=[];}
    const dialog=new frappe.ui.Dialog({title:__('Edit this project question'),size:'extra-large',fields:[
      ...(settings.protected?[{fieldname:'protected_help',fieldtype:'HTML',options:'<p>'+__('This required evidence check must remain. Adapt its question and capture subjects to the request; required media types and conditions are preserved.')+'</p>'}]:[]),
      {fieldname:'label',label:__('Question for the scout'),fieldtype:'Small Text',reqd:1},
      {fieldname:'instructions',label:__('Instructions / what a satisfactory answer must establish'),fieldtype:'Small Text'},
      {fieldname:'answer_format',label:__('Answer format'),fieldtype:'Select',options:settings.template?'Template format':'Single choice\nMultiple choice\nWritten answer',read_only:settings.template,reqd:1},
      {fieldname:'answer_options',label:settings.template?__('Template answer choices'):__('Answer choices, one per line'),fieldtype:'Small Text',read_only:settings.template,depends_on:"eval:doc.answer_format !== 'Written answer'"},
      ...(settings.configuration_template?scoutConfigurationFields(template):[]),
      {fieldname:'evidence_mode',label:__('Required evidence'),fieldtype:'Select',options:settings.template?'Keep template evidence\nSpecify evidence':'Specify evidence',reqd:1},
      {fieldname:'evidence',label:__('Photo, video or document requirements'),fieldtype:'Table',in_place_edit:true,depends_on:"eval:doc.evidence_mode === 'Specify evidence'",fields:[
        {fieldname:'id',fieldtype:'Data',hidden:1},
        {fieldname:'kind',label:__('Media'),fieldtype:'Select',options:'Photo\nVideo\nDocument',reqd:1,in_list_view:1},
        {fieldname:'subject',label:__('Exactly what the evidence must show'),fieldtype:'Small Text',reqd:1,in_list_view:1},
        {fieldname:'when',label:__('Only for these answer choices, separated by |'),fieldtype:'Small Text'},
        {fieldname:'once',label:__('One file can cover the assigned items'),fieldtype:'Check'},
        {fieldname:'caption',label:__('Automatic file label'),fieldtype:'Small Text'},
        {fieldname:'detail_when',label:__('Clarification for these outcomes, separated by |'),fieldtype:'Small Text'},
      ]},
    ],primary_action_label:__('Save question'),async primary_action(values) {
      if (!settings.template && values.answer_format!=='Written answer' && !values.answer_options?.trim()) {frappe.msgprint(__('Enter the answer choices first.'));return;}
      if (settings.configuration_template) await frappe.model.set_value(cdt,cdn,'configuration_json',JSON.stringify(scoutConfiguration(values,template)));
      const evidence=(values.evidence||[]).map((rule,index)=>({id:rule.id||scoutInternalId(),kind:rule.kind,subject:rule.subject,...(rule.when?{when:rule.when.split('|').map(v=>v.trim()).filter(Boolean)}:{}),...(rule.once?{once:true}:{}),...(rule.caption?{caption:rule.caption}:{}),...(rule.detail_when?{detail_when:rule.detail_when.split('|').map(v=>v.trim()).filter(Boolean)}:{})}));
      for (const key of ['label','instructions','answer_format','evidence_mode']) await frappe.model.set_value(cdt,cdn,key,values[key]||'');
      await frappe.model.set_value(cdt,cdn,'answer_options',settings.template?'':values.answer_options||'');
      await frappe.model.set_value(cdt,cdn,'evidence_json',JSON.stringify(evidence));
      await frm.set_value('scout_checks_confirmed',0);
      frm.refresh_field('scout_checks');dialog.hide();
    }});
    dialog.set_values({...saved,extra_capture:!!saved.additional_evidence?.length,enabled:saved.enabled??1,items:(saved.items||(template.default_items||[]).map(label=>({label}))).map(item=>({...item,id:item.id||scoutInternalId(),media:item.evidence?.length===2?'Photo and video':item.evidence?.[0]?.kind||'No media',subject:item.evidence?.[0]?.subject,when:item.evidence?.[0]?.when?.join('|')})),additional_evidence:(saved.additional_evidence||[]).map(rule=>({id:rule.id.replace(/-(photo|video|document)$/,''),media:rule.kind,subject:rule.subject,when:rule.when?.join('|')})),label:row.label||'',instructions:row.instructions||'',answer_format:settings.template?'Template format':row.answer_format==='Template format'?'Written answer':row.answer_format||'Written answer',answer_options:settings.template?settings.options.join('\n'):row.answer_options||'',evidence_mode:settings.template?(row.evidence_mode||'Keep template evidence'):'Specify evidence',evidence:rules.map(rule=>({...rule,when:rule.when?.join('|'),detail_when:rule.detail_when?.join('|')}))});
    dialog.show();
  }
});
