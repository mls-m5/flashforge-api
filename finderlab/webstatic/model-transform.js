// Geometry math shared by controller/scene tests. Coordinates in mm, angles in degrees.
export function normalizeTransform(value) {
    const defaults={scale:1,rotate_x:0,rotate_y:0,rotate_z:0,x:0,y:0};
    if(!value||typeof value!=='object'||Array.isArray(value)||Object.keys(value).some(k=>!Object.prototype.hasOwnProperty.call(defaults,k)))throw Error('Unknown transform fields.');
    const t={...defaults,...value};
    for(const [key,n] of Object.entries(t)){
        const [low,high]=key==='scale'?[.01,10]:['x','y'].includes(key)?[-70,70]:[-360,360];
        if(typeof n!=='number'||!Number.isFinite(n)||n<low||n>high)throw Error(`${key} must be finite in [${low}, ${high}].`);
    }return t;
}
export function modelLayout(positions,options={}) {
    const t=normalizeTransform(options),box=[[Infinity,-Infinity],[Infinity,-Infinity],[Infinity,-Infinity]];
    for(let i=0;i<positions.length;i++){const a=i%3;box[a][0]=Math.min(box[a][0],positions[i]);box[a][1]=Math.max(box[a][1],positions[i]);}
    const center=box.map(b=>(b[0]+b[1])/2);
    const [x,y,z]=[t.rotate_x,t.rotate_y,t.rotate_z].map(d=>d*Math.PI/180);
    const cx=Math.cos(x),sx=Math.sin(x),cy=Math.cos(y),sy=Math.sin(y),cz=Math.cos(z),sz=Math.sin(z);
    const r=[cz*cy,cz*sy*sx-sz*cx,cz*sy*cx+sz*sx,sz*cy,sz*sy*sx+cz*cx,sz*sy*cx-cz*sx,-sy,cy*sx,cy*cx].map(n=>n*t.scale);
    const rb=[[Infinity,-Infinity],[Infinity,-Infinity],[Infinity,-Infinity]];
    for(let i=0;i<positions.length;i+=3){
        for(let a=0;a<3;a++){
            const n=r[a*3]*(positions[i]-center[0])+r[a*3+1]*(positions[i+1]-center[1])+r[a*3+2]*(positions[i+2]-center[2]);
            rb[a][0]=Math.min(rb[a][0],n);rb[a][1]=Math.max(rb[a][1],n);
        }
    }
    const offset=[t.x-(rb[0][0]+rb[0][1])/2,t.y-(rb[1][0]+rb[1][1])/2,-rb[2][0]];
    const translation=offset.map((n,a)=>n-r[a*3]*center[0]-r[a*3+1]*center[1]-r[a*3+2]*center[2]);
    const bounds=rb.map((b,a)=>b.map(n=>n+offset[a]));
    const matrix=[...r.slice(0,3),translation[0],...r.slice(3,6),translation[1],...r.slice(6,9),translation[2],0,0,0,1];
    return {matrix,bounds,dimensions:bounds.map(b=>b[1]-b[0]),fits:bounds[0][0]>=-70-1e-5&&bounds[0][1]<=70+1e-5&&bounds[1][0]>=-70-1e-5&&bounds[1][1]<=70+1e-5&&bounds[2][1]<=140+1e-5};
}
