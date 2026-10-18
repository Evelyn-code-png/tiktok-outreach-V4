'use strict';
(() => {
 const labels={accepted_by_smtp:'Sent — accepted by Gmail',failed_before_submission:'Not sent — submission failed',rejected:'Failed — rejected by Gmail',unknown:'Unconfirmed — check Gmail Sent',sending:'Unconfirmed — check Gmail Sent',suppressed:'Skipped — do not contact',sent_browser:'Sent through Gmail browser'};
 function describe(job){
  const rows=(job.result?.results||[]).map(r=>({email:r.email,label:r.skipped?'Skipped — already processed or do not contact':labels[r.status]||r.status}));
  if(['queued','running'].includes(job.status))return {tone:'progress',busy:true,title:job.status==='queued'?'Waiting to send…':'Sending…',message:job.progress?`Processed ${job.progress.completed} of ${job.progress.total} messages. Do not submit this batch again.`:'The sending task is starting. Do not submit this batch again.',rows};
  const result=job.result;
  if(!result)return {tone:'warning',title:job.status==='failed'?'Sending failed':'Sending stopped — review required',message:(job.error||'The task ended without a final sending report.')+' Check Delivery log and Gmail Sent before retrying; some messages may have been submitted.',rows};
  const attempted=(result.results||[]).filter(r=>!r.skipped);
  const accepted=Number.isInteger(result.accepted)?result.accepted:attempted.filter(r=>r.status==='accepted_by_smtp').length;
  const failed=attempted.filter(r=>['failed_before_submission','rejected'].includes(r.status)).length;
  const unconfirmed=Math.max(attempted.filter(r=>!['accepted_by_smtp','failed_before_submission','rejected'].includes(r.status)).length,(result.failed_or_unknown||0)-failed);
  const skipped=Number.isInteger(result.skipped)?result.skipped:(result.results||[]).filter(r=>r.skipped).length;
  const counts=`${accepted} sent · ${failed} failed · ${unconfirmed} unconfirmed · ${skipped} skipped.`;
  if(['failed','interrupted','cancelled'].includes(job.status))return {tone:'warning',title:'Sending stopped — review required',message:counts+' '+(job.error||'The batch was stopped.')+' Check Delivery log before sending any remaining messages.',rows};
  if(unconfirmed)return {tone:'warning',title:'Some sending results are unconfirmed',message:counts+' Check Gmail Sent and Delivery log before retrying. Unconfirmed messages are not retried automatically.',rows};
  if(failed)return {tone:accepted?'warning':'error',title:accepted?'Part of the batch was sent':'Sending failed',message:counts+' The batch stopped after a failure. Any remaining recipients were not attempted. No automatic retry was made.',rows};
  if(accepted)return {tone:'success',title:'Sent — accepted by Gmail',message:counts+' Gmail accepted these messages for sending. Inbox delivery and read status are not confirmed.',rows};
  if(skipped)return {tone:'info',title:'No new emails sent',message:counts+' These recipients were already processed or are on the do not contact list.',rows};
  return {tone:'warning',title:'Send result needs review',message:'No recipient outcome was reported. Check Delivery log before trying again.',rows};
 }
 if(typeof module!=='undefined'&&module.exports)module.exports={describe};else window.OutreachSendFeedback={describe};
})();
