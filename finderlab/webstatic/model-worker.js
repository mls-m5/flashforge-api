/* Bounded geometry-only STL reader. No fetching, placement edits, repair or slicing. */
"use strict";
function parseModel(buffer) {
    if (!buffer.byteLength || buffer.byteLength > 32*1024*1024) throw new Error('Model preview limit: 32 MiB. Slicing remains independent.');
    const max = 200000, data = new DataView(buffer);
    let positions, count = 0;
    const facetCount = buffer.byteLength >= 84 ? data.getUint32(80, true) : -1;
    if (facetCount >= 0 && 84 + facetCount * 50 === buffer.byteLength) {
        if (!facetCount || facetCount > max) throw new Error('Model preview requires 1–200,000 triangles.');
        positions = new Float32Array(facetCount * 9);
        for (let i=0; i<facetCount; i++) {
            for (let j=0; j<9; j++) positions[i*9+j] = data.getFloat32(84+i*50+12+j*4, true);
        }
        count = facetCount;
    } else {
        const text = new TextDecoder('utf-8', {fatal:true}).decode(buffer);
        if (!/^\s*solid(?:\s|$)/i.test(text) || text.includes('\0')) throw new Error('Expected binary or ASCII STL geometry.');
        const vertices = []; let inFacet=false, facetVertices=0;
        const numeric='[+-]?(?:\\d+(?:\\.\\d*)?|\\.\\d+)(?:[eE][+-]?\\d+)?';
        const vertex=new RegExp('^vertex\\s+('+numeric+')\\s+('+numeric+')\\s+('+numeric+')\\s*$','i');
        let start=0, lines=0;
        while(start<text.length) {
            let end=text.indexOf('\n',start); if(end<0)end=text.length;
            const raw=text.slice(start,end);start=end+1;
            if(raw.length>4096 || ++lines>2000000)throw new Error('STL line limit exceeded.');
            const line=raw.trim(); if(!line)continue;
            if(/^facet\s+normal\s+/i.test(line)) {
                if(inFacet)throw new Error('Nested STL facet.');inFacet=true;facetVertices=0;
            } else if(/^vertex\s/i.test(line)) {
                const match=vertex.exec(line);
                if(!inFacet || !match || ++facetVertices>3)throw new Error('Malformed STL vertex/facet.');
                vertices.push(Number(match[1]),Number(match[2]),Number(match[3]));
                if(vertices.length>max*9)throw new Error('Model preview exceeds 200,000 triangles.');
            } else if(/^endfacet$/i.test(line)) {
                if(!inFacet || facetVertices!==3)throw new Error('Incomplete STL triangle.');
                inFacet=false;count++;
            } else if(!/^(?:solid(?:\s.*)?|endsolid(?:\s.*)?|outer\s+loop|endloop)$/i.test(line)) {
                throw new Error('Unsupported ASCII STL syntax.');
            }
        }
        if(inFacet || !count || vertices.length!==count*9)throw new Error('Incomplete/empty STL.');
        positions=new Float32Array(vertices);
    }
    const bounds=[[Infinity,-Infinity],[Infinity,-Infinity],[Infinity,-Infinity]];
    for(let i=0;i<positions.length;i++) {
        const value=positions[i];
        if(!Number.isFinite(value) || Math.abs(value)>100000)throw new Error('STL coordinate exceeds preview bounds.');
        bounds[i%3][0]=Math.min(bounds[i%3][0],value);bounds[i%3][1]=Math.max(bounds[i%3][1],value);
    }
    const normals=new Float32Array(positions.length);let degenerate=0;
    for(let i=0;i<positions.length;i+=9) {
        const ax=positions[i+3]-positions[i],ay=positions[i+4]-positions[i+1],az=positions[i+5]-positions[i+2];
        const bx=positions[i+6]-positions[i],by=positions[i+7]-positions[i+1],bz=positions[i+8]-positions[i+2];
        const nx=ay*bz-az*by,ny=az*bx-ax*bz,nz=ax*by-ay*bx,length=Math.hypot(nx,ny,nz);
        if(!length){degenerate++;continue;}
        for(let j=0;j<3;j++)normals.set([nx/length,ny/length,nz/length],i+j*3);
    }
    if(degenerate===count)throw new Error('No nonzero-area triangles to preview.');
    return {positions,normals,triangles:count,degenerate,bounds,dimensions:bounds.map(b=>b[1]-b[0])};
}
if(typeof module!=='undefined')module.exports={parseModel};
if(typeof self!=='undefined' && typeof self.postMessage==='function')self.onmessage=event=>{
    try{const result=parseModel(event.data.buffer);self.postMessage({result},[result.positions.buffer,result.normals.buffer]);}
    catch(error){self.postMessage({error:error.message});}
};
