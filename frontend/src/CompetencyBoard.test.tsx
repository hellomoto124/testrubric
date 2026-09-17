import '@testing-library/jest-dom/vitest';
import {render,screen,fireEvent,cleanup,within} from '@testing-library/react';
import {afterEach,expect,test,vi} from 'vitest';
import CompetencyBoard,{tenCapabilityOption} from './CompetencyBoard';

afterEach(()=>{cleanup();vi.unstubAllGlobals();});
const names=['通情达理','公共参与','多元共生','明己励志','参与探究','解决问题','表达想法','学会学习','读懂世界','定量推理'];
const caps=names.map((name,i)=>({code:`YY.C${String(i+1).padStart(2,'0')}`,name,goal_code:i<3?'YY.G01':i<7?'YY.G02':'YY.G03',goal_name:i<3?'关怀者':i<7?'创造者':'学习者',state:'partial' as const,median_level:i===9?null:3,assessed_count:1,skill_count:3,coverage:1/3,recorded_count:1,missing_count:2,review_count:0,target_met_count:1}));
const goals=['关怀者','创造者','学习者'].map((name,i)=>({code:`YY.G0${i+1}`,name,short_name:name,capabilities:caps.filter(c=>c.goal_code===`YY.G0${i+1}`)}));
const students=[1,2].map(id=>({id,anonymous_id:`模拟学生0${id}`,class_id:1,class_name:'模拟班级1',capabilities:caps,goals:[]}));
test('ten-dimensional chart leaves unknown empty',()=>{
 const option=tenCapabilityOption(caps);
 expect((option.angleAxis as {data:string[]}).data).toHaveLength(10);
 expect((option.series as {data:{value:number|null}[]}[])[0].data[9].value).toBeNull();
});
test('matrix groups ten school capabilities and opens scoped evidence request',async()=>{
 const mock=vi.fn(async(input:RequestInfo|URL)=>({ok:true,json:async()=>String(input).includes('/capabilities/')?{student:{id:1,name:'模拟学生01'},capability:caps[0],skills:[]}:{goals,students,stages:[],summary:{student_count:2,recorded_skills:20,missing_skills:40,review_skills:0},methodology:'按技能聚合'}}));
 vi.stubGlobal('fetch',mock);
 HTMLDialogElement.prototype.showModal=function(){this.setAttribute('open','');};
 render(<CompetencyBoard context={{classes:[{id:1,name:'模拟班级1'}]}} openStudent={vi.fn()}/>);
 const matrix=await screen.findByRole('table',{name:'学生十项核心素养矩阵'});
 for(const name of names)expect(within(matrix).getByRole('columnheader',{name})).toBeInTheDocument();
 fireEvent.click(within(matrix).getByRole('button',{name:'模拟学生01 通情达理 部分已评'}));
 expect(await screen.findByRole('dialog',{name:'素养证据详情'})).toBeInTheDocument();
 expect(mock).toHaveBeenCalledWith('/api/v2/students/1/capabilities/YY.C01?stage=latest',expect.anything());
});
