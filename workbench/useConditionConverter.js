/*! 

     */
function c(i,e={}){const o={type:"STRING",operator:"LIKE",ignoreEmpty:!0};return{convertToConditions:()=>Object.entries(i).filter(([n,t])=>!(e[n]||o).ignoreEmpty||t!==""&&t!==null&&t!==void 0).map(([n,t])=>{const r=e[n]||o;return{field:n,type:r.type||o.type,operator:r.operator||o.operator,value:String(t)}})}}export{c as u};
