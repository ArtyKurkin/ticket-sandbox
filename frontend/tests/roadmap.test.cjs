const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');

function loadModule(name) {
  const filename = path.join(__dirname, '../src/roadmap', name + '.ts');
  const compiled = ts.transpileModule(fs.readFileSync(filename, 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  }).outputText;
  const context = { exports: {} };
  vm.runInNewContext(compiled, context, { filename });
  return context.exports;
}
const { positionCard } = loadModule('positioning');
function intersects(a,b) {
  return a.left < b.left+b.width && a.left+a.width > b.left && a.top < b.top+b.height && a.top+a.height > b.top;
}

test('inspector avoids other stations and labels in its preferred location', () => {
  const bounds={width:1000,height:800},card={width:330,height:240};
  const anchor={left:400,top:200,width:130,height:180};
  const obstacles=[anchor,{left:550,top:180,width:160,height:190},{left:220,top:480,width:180,height:70}];
  const result=positionCard(bounds,card,anchor,obstacles,'right');
  assert.equal(result.intersections,0);
  for(const obstacle of obstacles) assert(!intersects({...result,...card},obstacle));
  assert(result.left>=16 && result.top>=16 && result.left+card.width<=bounds.width-16 && result.top+card.height<=bounds.height-16);
});

test('measurements with inherited DOMRect dimensions are accepted', () => {
  const card=Object.create({width:330,height:240});
  const anchor={left:100,top:200,width:130,height:180};
  const result=positionCard({width:1000,height:800},card,anchor,[anchor],'right');
  assert.equal(result.intersections,0);
  assert(Number.isFinite(result.left) && Number.isFinite(result.top));
  assert(!intersects({...result,width:card.width,height:card.height},anchor));
});

test('edge stations keep the inspector inside the workspace', () => {
  const bounds={width:1100,height:730},card={width:330,height:240};
  const anchor={left:980,top:610,width:100,height:100};
  const result=positionCard(bounds,card,anchor,[anchor],'right');
  assert.equal(result.intersections,0);
  assert(result.left+card.width<=bounds.width-16 && result.top+card.height<=bounds.height-16);
});

test('insufficient room is detected and reserved scroll space removes intersections', () => {
  const card={width:330,height:240};
  const anchor={left:0,top:0,width:500,height:400};
  const compact=positionCard({width:500,height:400},card,anchor,[anchor],'right');
  assert(compact.intersections>0);
  const extended=positionCard({width:500,height:700},card,anchor,[anchor],'right');
  assert.equal(extended.intersections,0);
  assert(!intersects({...extended,...card},anchor));
});
