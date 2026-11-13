export interface BlankPreview{rows:number;complete:number;degreesOfFreedom:number;issues:string[];valid:boolean}

export function parseBlankReadings(text:string,bandCount:number):BlankPreview{
  const issues:string[]=[];
  if(bandCount<1)return {rows:0,complete:0,degreesOfFreedom:0,issues,valid:false};
  const lines=text.split(/\r?\n/).map((line)=>line.trim()).filter((line)=>line.length>0);
  const rows:number[][]=[];
  lines.forEach((line,index)=>{
    const values=line.split(/[,，\s]+/).filter((part)=>part.length>0);
    if(values.length!==bandCount){issues.push(`第${index+1}次读数含${values.length}个值，应为${bandCount}个波段（缺波段或多余波段不能静默忽略）`);return}
    if(values.some((part)=>!Number.isFinite(Number(part)))){issues.push(`第${index+1}次读数含非数字或非有限值`);return}
    rows.push(values.map(Number));
  });
  const complete=rows.length;
  return {rows:lines.length,complete,degreesOfFreedom:Math.max(complete-1,0),issues,valid:issues.length===0&&complete>bandCount};
}

export function blankText(readings:number[][]):string{
  return readings.map((row)=>row.join(', ')).join('\n');
}
