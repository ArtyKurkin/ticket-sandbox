const fs = require('node:fs');
const path = require('node:path');
const ts = require('typescript');
const nativeRequire = require;
function modules(overrides = {}, folder = 'roadmap') {
  const cache = new Map();
  function load(name) {
    const root = path.resolve(__dirname, '../src', folder);
    const filename = path.resolve(root, name);
    const resolved = ['.ts', '.tsx', ''].map(ext => filename + ext).find(file => fs.existsSync(file));
    if (!resolved) throw new Error('Missing module: ' + filename);
    const short = path.relative(root, resolved).replace(/\.tsx?$/, '');
    if (overrides[short]) return overrides[short];
    if (cache.has(resolved)) return cache.get(resolved).exports;
    const module = { exports: {} }; cache.set(resolved, module);
    const code = ts.transpileModule(fs.readFileSync(resolved, 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX } }).outputText;
    const localRequire = id => overrides[id] ?? (id.startsWith('.') ? load(path.relative(root, path.resolve(path.dirname(resolved), id))) : nativeRequire(id.startsWith('react') ? path.resolve(__dirname, '../node_modules', id) : id));
    new Function('module', 'exports', 'require', code)(module, module.exports, localRequire);
    return module.exports;
  }
  return load;
}
function fixture(name) { return JSON.parse(fs.readFileSync(path.resolve(__dirname, '../../roadmap/examples', name + '.json'), 'utf8')); }
module.exports = { modules, fixture };
