import {expect,test} from '@playwright/test';

test('ten-capability matrix filters, compares, and drills into real simulated evidence',async({page})=>{
 await page.goto('/');
 await page.getByRole('navigation',{name:'主导航'}).getByRole('button',{name:/素养成长看板/}).click();
 const table=page.getByRole('table',{name:'学生十项核心素养矩阵'});
 await expect(table.locator('tbody tr')).toHaveCount(20);
 await expect(table.getByRole('columnheader',{name:/关怀者/})).toHaveAttribute('colspan','3');
 await expect(table.getByRole('columnheader',{name:/创造者/})).toHaveAttribute('colspan','4');
 await expect(table.getByRole('columnheader',{name:/学习者/})).toHaveAttribute('colspan','3');
 await expect(table.locator('tbody tr').first().getByRole('button')).toHaveCount(11);
 await page.getByLabel('班级',{exact:true}).selectOption('1');
 await expect(table.locator('tbody tr')).toHaveCount(7);
 await page.getByPlaceholder('搜索匿名学生').fill('01');
 await expect(table.locator('tbody tr')).toHaveCount(1);
 await page.getByPlaceholder('搜索匿名学生').fill('');
 await expect(table.locator('tbody tr')).toHaveCount(7);
 await page.getByLabel('对比模拟学生01',{exact:true}).check();
 await page.getByLabel('对比模拟学生02',{exact:true}).check();
 await expect(page.locator('.profile-comparison article')).toHaveCount(2);
 await table.getByRole('button',{name:/模拟学生01 定量推理/}).click();
 const dialog=page.getByRole('dialog',{name:'素养证据详情'});
 await expect(dialog.getByRole('heading',{name:'定量推理',exact:true})).toBeVisible();
 await expect(dialog.getByText(/校园数据小调查/).first()).toBeVisible();
 await expect(dialog.getByText('可比成长记录（3）')).toBeVisible();
 await dialog.getByRole('button',{name:'关闭素养详情'}).click();
 await expect(dialog).toHaveCount(0);
 await table.getByRole('button',{name:'模拟学生01',exact:true}).click();
 await expect(page.locator('.board-person .capability-tile')).toHaveCount(10);
 await page.getByRole('button',{name:'打开完整成长档案'}).click();
 await expect(page.locator('.student-competency-module .capability-tile')).toHaveCount(10);
 await expect(page.locator('.identity-goal')).toHaveCount(3);
});

test('stages and mentor view stay usable at phone tablet and desktop widths',async({page})=>{
 for(const width of [375,768,1440]){
  await page.setViewportSize({width,height:900});
  await page.goto('/');
  await page.getByRole('navigation',{name:'主导航'}).getByRole('button',{name:/素养成长看板/}).click();
  await expect(page.getByRole('table',{name:'学生十项核心素养矩阵'}).locator('tbody tr')).toHaveCount(20);
  await page.getByLabel('观察阶段').selectOption('baseline');
  await page.getByLabel('育人目标',{exact:true}).selectOption('YY.G03');
  await expect(page.getByRole('table',{name:'学生十项核心素养矩阵'}).locator('thead tr').last().locator('th')).toHaveCount(3);
  await page.getByRole('button',{name:'学情摘要',exact:true}).click();
  await expect(page.getByRole('heading',{name:'当前筛选学情摘要'})).toBeVisible();
  await page.getByRole('button',{name:'导师关注视图',exact:true}).click();
  await expect(page.getByRole('heading',{name:'导师关注清单'})).toBeVisible();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=document.documentElement.clientWidth)).toBe(true);
 }
});
