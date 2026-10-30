'use strict';

// The image and CSV use the same focused levels and category pages as the screen.
const comparisonExport = (() => {
  const pct = value => value.toLocaleString(undefined, {maximumFractionDigits: 1}) + '%';
  function csvCell(value) {
    let result = String(value ?? '');
    if (typeof value === 'string' && /^[=+@-]/.test(result.replace(/^[\s\p{Cc}\p{Cf}]+/u, ''))) result = "'" + result;
    return '"' + result.replaceAll('"', '""') + '"';
  }
  function csv(model) {
    const rows = [['Source file','Review ID','Scope','Level','Field','Parent path','Category','Records','Percent',
      'Percentage denominator','Percentage basis','Selected on path','Visible in PNG','Multiple selections','Exported UTC',
      'Records with findings','Flagged percent','Row type','Concentration scope']];
    for (const level of model.levels) {
      for (const group of level.groups) rows.push([model.file,model.run,model.scope,level.index + 1,level.title,
        level.parentPath.map(item => item.title + ': ' + item.value).join(' / '),group.label,group.count,group.percent,
        level.denominator,model.portfolio ? '% of all records' : '% of parent records',
        group.label === level.selected ? 'Yes' : 'No',level.visible.includes(group) ? 'Yes' : 'No',level.multi ? 'Yes' : 'No',model.stamp,
        group.flagged,level.denominator ? 100*group.flagged/level.denominator : 0,'Drill-down category','']);
    }
    const c=model.concentration;
    for(const group of c.all)rows.push([model.file,model.run,model.scope,'',c.label,
      c.scope==='Selected path'?model.path.map(item=>item.title+': '+item.value).join(' / '):'Current view',
      group.label,group.count,group.percent,c.denominator,model.portfolio?'% of all records':'% of records in this scope',
      '',c.visible.includes(group)?'Yes':'No','Yes; groups can overlap',model.stamp,group.count,group.percent,'Validation concentration',c.scope]);
    return '\ufeff' + rows.map(row => row.map(csvCell).join(',')).join('\r\n');
  }
  async function png(model) {
    const canvas = document.createElement('canvas');
    canvas.width = 1920; canvas.height = 1080;
    const pen = canvas.getContext('2d');
    pen.scale(1.5,1.5);
    const ink = '#172f45', muted = '#586e81', accent = '#087f87', line = '#d9e3ec';
    const font = (size, bold = false) => (bold ? '600 ' : '') + size + 'px Arial, sans-serif';
    function text(value,x,y,size=12,color=ink,bold=false,align='left') {
      pen.font=font(size,bold); pen.fillStyle=color; pen.textAlign=align; pen.textBaseline='top';pen.fillText(String(value),x,y);
    }
    function fit(value,width,size,bold=false) {
      let result=String(value);pen.font=font(size,bold);
      if (pen.measureText(result).width<=width) return result;
      while (result && pen.measureText(result+'…').width>width) result=result.slice(0,-1);
      return result+'…';
    }
    function wrap(value,x,y,width,size,maxLines=2,color=ink,bold=false) {
      pen.font=font(size,bold);
      const words=String(value).split(/\s+/);let current='';const lines=[];
      for (const word of words) {
        if (current && pen.measureText(current+' '+word).width>width) {lines.push(current);current=word;}
        else current+=(current?' ':'')+word;
      }
      if(current) lines.push(current);
      if(lines.length>maxLines) lines.splice(maxLines-1,lines.length-maxLines+1,fit(lines.slice(maxLines-1).join(' '),width,size,bold));
      lines.forEach((part,index)=>text(fit(part,width,size,bold),x,y+index*(size+3),size,color,bold));
    }
    function box(x,y,w,h,fill,border='',radius=8) {
      pen.beginPath();pen.roundRect(x,y,w,h,radius);pen.fillStyle=fill;pen.fill();
      if(border){pen.strokeStyle=border;pen.lineWidth=1;pen.stroke();}
    }
    box(0,0,1280,720,'#f1f5f9','',0);box(0,0,1280,6,accent,'',0);
    text('AI INVENTORY / DRILL-DOWN',32,25,11,accent,true);
    text(model.title,32,45,28,ink,true);
    text(fit(model.filterContext,630,9),32,76,9,muted);
    const metrics=[['RECORDS IN SCOPE',model.scopeCount.toLocaleString()],['MATCHING RECORDS',model.focusCount.toLocaleString()],
      ['FLAGGED IN PATH',model.focusFlagged.toLocaleString()],['PATH SHARE OF '+model.population,pct(model.focusPercent)]];
    metrics.forEach(([label,value],index)=>{const x=705+index*137;text(value,x,25,27,ink,true);text(label,x,57,9,muted,true);});
    const chipWidth=(1216-12*(model.path.length-1))/Math.max(1,model.path.length);
    model.path.forEach((part,index)=>{
      const x=32+index*(chipWidth+12);box(x,89,chipWidth,42,'#e2eef0','',5);
      text(index+1,x+10,101,12,accent,true);
      wrap(part.value,x+30,96,chipWidth-40,12,2,ink,true);
      if(index<model.path.length-1)text('›',x+chipWidth+2,100,18,accent,true);
    });
    if(!model.path.length)text('No matching records',32,102,13,muted);
    const rows=model.dense?2:1;
    const columns=model.dense?(model.levels.length===4?2:3):model.levels.length;
    const gap=14, areaY=149, areaH=513, rowH=(areaH-gap*(rows-1))/rows;
    const sidebar=220, bodyX=32+sidebar+gap, bodyW=1216-sidebar-gap;
    const c=model.concentration;
    box(32,areaY,sidebar,areaH,'#ffffff',line,9);
    text('Validation concentration',46,areaY+15,14,ink,true);
    text(c.scope+' · '+c.total+' records',46,areaY+39,10,muted);
    wrap(model.filterContext,46,areaY+55,sidebar-28,9,2,muted);
    text(c.flagged,46,areaY+87,35,'#a43c53',true);
    text('records with findings',46,areaY+127,12,ink,true);
    text(pct(c.percent)+' of '+c.denominator+' records',46,areaY+147,10,muted);
    text(c.passed+' pass · '+c.instances+' finding instances',46,areaY+169,9,muted);
    text(c.label.toUpperCase(),46,areaY+200,9,accent,true);
    c.visible.forEach((group,index)=>{
      const y=areaY+226+index*33;
      text(fit(group.label,sidebar-53,10),46,y,10,ink);
      text(group.count,32+sidebar-14,y,11,ink,true,'right');
      box(46,y+17,sidebar-28,4,'#eaf0f5','',2);
      box(46,y+17,(sidebar-28)*group.count/c.max,4,'#bb5268','',2);
    });
    wrap((c.all.length>7?'Top 7 of '+c.all.length+' groups. ':'')+'Distinct records per group. Groups can overlap.',46,areaY+areaH-48,sidebar-28,9,3,muted);
    function layout(index) {
      if(model.levels.length===5 && index>=3){const w=(bodyW-gap)/2;return {x:bodyX+(index-3)*(w+gap),y:areaY+rowH+gap,w,h:rowH};}
      const w=(bodyW-gap*(columns-1))/columns;
      return {x:bodyX+(index%columns)*(w+gap),y:areaY+Math.floor(index/columns)*(rowH+gap),w,h:rowH};
    }
    model.levels.forEach(level=>{
      const {x,y,w,h}=layout(level.index),pad=14;
      box(x,y,w,h,'#ffffff',line,9);
      text('LEVEL '+(level.index+1),x+pad,y+11,9,accent,true);
      text(fit(level.title,w-2*pad,15,true),x+pad,y+25,15,ink,true);
      const context=(level.parentPath.length?'Within '+level.parentPath.at(-1).value:model.scope)+' · '+level.parentCount+' records';
      text(fit(context,w-2*pad,10.5),x+pad,y+45,10.5,muted);
      const chartY=y+65, chartH=model.dense?48:155;
      text('Flagged / total'+(level.groups.length && level.selectedPage!==level.page?' · selection on page '+(level.selectedPage+1):''),x+pad,chartY,8,muted);
      text('0 – '+level.max,x+w-pad,chartY,9,muted,false,'right');
      const slot=(chartH-16)/level.pageSize;
      level.visible.forEach((group,index)=>{
        const gy=chartY+16+index*slot;
        const labelW=(w-2*pad)*.41;
        const trackX=x+pad+labelW+7,trackW=w-2*pad-labelW-46;
        text(fit(group.label,labelW,model.dense?9:11),x+pad,gy,model.dense?9:11,
          group.label===level.selected?ink:muted,group.label===level.selected);
        box(trackX,gy+3,trackW,6,'#eaf0f5','',3);
        box(trackX,gy+3,trackW*group.flagged/level.max,6,'#bb5268','',0);
        box(trackX+trackW*group.flagged/level.max,gy+3,trackW*(group.count-group.flagged)/level.max,6,'#289c96','',0);
        text(group.flagged+'/'+group.count,x+w-pad,gy,model.dense?9:11,ink,true,'right');
      });
      if(!level.groups.length)text('No matching records',x+pad,chartY+25,12,muted);
      const tableY=chartY+chartH+(model.dense?8:12),headH=model.dense?18:25,rowHeight=model.dense?22:36;
      box(x+pad,tableY,w-2*pad,headH,'#edf3f7','',0);
      const countX=x+w-110,flagX=x+w-64,shareX=x+w-pad-4,nameW=w-2*pad-140;
      text('CATEGORY',x+pad+7,tableY+6,8,muted,true);
      text('RECORDS',countX,tableY+6,8,muted,true,'right');
      text('FLAGGED',flagX,tableY+6,8,muted,true,'right');
      text('SHARE',shareX,tableY+6,8,muted,true,'right');
      level.visible.forEach((group,index)=>{
        const ry=tableY+headH+index*rowHeight;
        const selected=group.label===level.selected;
        box(x+pad,ry,w-2*pad,rowHeight,selected?'#e1f0ef':(index%2?'#f6f8fa':'#ffffff'),'',0);
        if(selected)box(x+pad,ry,3,rowHeight,accent,'',0);
        if(model.dense)text(fit(group.label,nameW,11,selected),x+pad+7,ry+7,11,ink,selected);
        else wrap(group.label,x+pad+7,ry+6,nameW,11.5,2,ink,selected);
        text(group.count,countX,ry+7,12,ink,true,'right');
        text(group.flagged,flagX,ry+7,12,'#a43c53',true,'right');
        text(pct(group.percent),shareX,ry+7,11,muted,false,'right');
      });
      const basis='Share of '+level.denominator+' records '+(model.portfolio?'in file':'in parent');
      text(basis,x+pad,y+h-29,9,muted);
      const start=level.groups.length?level.page*level.pageSize+1:0;
      text(start+'–'+Math.min((level.page+1)*level.pageSize,level.groups.length)+' of '+level.groups.length+' categories',
        x+w-pad,y+h-16,9,muted,false,'right');
    });
    text(fit('Source: '+model.file+' · '+model.scope+' · Exported '+model.stamp.slice(0,10),600,10),32,678,10,muted);
    const note=(model.portfolio?'% of all '+model.population+' records.':'% of parent records.')+' Flagged = records with findings.';
    text(fit(note,600,10),1248,678,10,muted,false,'right');
    text('Red: with findings. Teal: no findings. Groups can overlap. Tables show the current page; CSV includes every category.',32,698,9,muted);
    const blob=await new Promise(resolve=>canvas.toBlob(resolve,'image/png'));
    if(!blob)throw new Error('Unable to export this view. Try again.');
    return blob;
  }
  return {csv,png};
})();
