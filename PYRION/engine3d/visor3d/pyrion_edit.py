#!/usr/bin/env python3
# PYRION EDIT - Editor de mallas .mesh (PySide6 + Qt WebEngine)
# PySide6 se instala automaticamente si falta.
import json
import base64
import os
import urllib.error
import sys
import urllib.request
from pathlib import Path
from copy import deepcopy
import importlib.util
import subprocess

APP_VERSION = "1.3.4"

def ensure_pyside6():
    required = ["PySide6.QtCore", "PySide6.QtWidgets", "PySide6.QtWebEngineWidgets", "PySide6.QtWebChannel"]
    try:
        if all(importlib.util.find_spec(x) is not None for x in required):
            return
    except ModuleNotFoundError:
        pass
    print("PYRION EDIT: instalando PySide6 (solo la primera vez)...", flush=True)
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", "--disable-pip-version-check", "PySide6"],
        capture_output=True, text=True, creationflags=creationflags
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "Error desconocido").strip()
        raise RuntimeError("No se pudo instalar PySide6 automáticamente: " + detail[-900:])
    importlib.invalidate_caches()

try:
    ensure_pyside6()
except Exception as exc:
    import traceback
    traceback.print_exc()
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(0, str(exc), "PYRION EDIT - Dependencias", 0x10)
        except Exception:
            pass
    raise SystemExit(1)

from PySide6.QtCore import QObject, Qt, Slot
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QComboBox, QPushButton, QLabel, QFileDialog, QDoubleSpinBox, QCheckBox, QMessageBox,
    QGroupBox, QFormLayout, QInputDialog, QLineEdit, QToolButton, QScrollArea)
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebChannel import QWebChannel

REPO = "mobatfb/archmoba-dev"
REMOTE = "PYRION/engine3d/scenes/chest/models/chest.mesh"

HTML = r"""
<!doctype html><html><head><meta charset="utf-8">
<style>html,body{margin:0;height:100%;overflow:hidden;background:#101424;color:#eee;font:13px system-ui}
canvas{display:block;width:100%;height:100%;cursor:grab}
#hint{position:absolute;left:16px;bottom:13px;color:#b9bfdf;pointer-events:none;background:#111827b8;padding:7px 10px;border-radius:7px}</style>
<script src="qrc:///qtwebchannel/qwebchannel.js"></script></head><body>
<canvas id="c"></canvas><div id="hint">Arrastrar: girar · Rueda: zoom · Clic: seleccionar cara</div>
<script>
let mesh=null,selected=-1,selectedGroup=null,mirror=true,wire=true,material=true,surface=true,labels=true,spin=false;
let yaw=-0.55,pitch=0.27,zoom=2.5,bridge=null,drag=null;
new QWebChannel(qt.webChannelTransport,c=>{bridge=c.objects.bridge});
const cv=document.getElementById('c'),ctx=cv.getContext('2d');
function setMesh(x){mesh=x;draw()}
function setOptions(x){mirror=x.mirror;wire=x.wire;material=x.material;surface=x.surface;labels=x.labels;spin=x.spin;draw()}
function setSelected(x){selected=x;selectedGroup=null;draw()}
function setSelectedGroup(a,b){selected=-1;selectedGroup=[a,b];draw()}
function resize(){const r=cv.getBoundingClientRect(),d=window.devicePixelRatio||1;
cv.width=Math.floor(r.width*d);cv.height=Math.floor(r.height*d);draw()}
window.addEventListener('resize',resize);
function draw(){
 const w=cv.width,h=cv.height;if(!w||!h)return;
 ctx.fillStyle='#101424';ctx.fillRect(0,0,w,h);
 const gr=ctx.createRadialGradient(w/2,h/2,10,w/2,h/2,Math.max(w,h)*0.65);
 gr.addColorStop(0,'#29213e');gr.addColorStop(1,'#101424');
 ctx.fillStyle=gr;ctx.fillRect(0,0,w,h);
 if(!mesh)return;
 const vv=mesh.vertices, ff=mesh.faces;if(!vv.length)return;
 const min=[0,1,2].map(k=>Math.min(...vv.map(v=>v[k])));
 const max=[0,1,2].map(k=>Math.max(...vv.map(v=>v[k])));
 const center=min.map((v,k)=>(k===0&&mirror)?0:(v+max[k])/2);
 const dimension=Math.max(...max.map((v,k)=>(k===0&&mirror)?2*Math.max(Math.abs(v),Math.abs(min[k])):v-min[k]),0.01);
 const scale=Math.min(w,h)*0.72/dimension;
 const vertices=vv.map(v=>{const x=v[0]-center[0],y=v[1]-center[1],z=v[2]-center[2];
 const rx=x*Math.cos(yaw)+z*Math.sin(yaw),rz=-x*Math.sin(yaw)+z*Math.cos(yaw);
 const py=y*Math.cos(pitch)-rz*Math.sin(pitch),pz=y*Math.sin(pitch)+rz*Math.cos(pitch);
 const k=zoom/(zoom+pz*0.6+3);return [w/2+rx*scale*k,h/2-py*scale*k,pz,k]});
 let polygons=[];
 function addFace(face,i,reflected){
   const p=face.map(j=>vertices[j]);if(p.length<3)return;
   const id=mesh.face_ids?.[i]||i+1;
   const color=material?(mesh.face_colors?.[i]||'#9062d6'):'#8986a1';
   polygons.push({p,i,id:reflected?id+ff.length:id,reflected,color,
     depth:p.reduce((a,v)=>a+v[2],0)/p.length});
 }
 ff.forEach((f,i)=>addFace(f,i,false));
 if(mirror){
   // Dibuja la mitad reflejada con la misma perspectiva, sin duplicar vertices reales.
   const mirrored=vv.map(v=>[-v[0],v[1],v[2]]).map(v=>{const x=v[0]-center[0],y=v[1]-center[1],z=v[2]-center[2];
      const rx=x*Math.cos(yaw)+z*Math.sin(yaw),rz=-x*Math.sin(yaw)+z*Math.cos(yaw);
      const py=y*Math.cos(pitch)-rz*Math.sin(pitch),pz=y*Math.sin(pitch)+rz*Math.cos(pitch);
      const k=zoom/(zoom+pz*0.6+3);return [w/2+rx*scale*k,h/2-py*scale*k,pz,k]});
   ff.forEach((f,i)=>{if(f.every(j=>Math.abs(vv[j][0])<0.00001))return;
     const p=f.map(j=>mirrored[j]);polygons.push({p,i,id:(mesh.face_ids?.[i]||i+1)+ff.length,
       reflected:true,color:material?(mesh.face_colors?.[i]||'#9062d6'):'#8986a1',
       depth:p.reduce((a,v)=>a+v[2],0)/p.length})});
 }
 polygons.sort((a,b)=>a.depth-b.depth);window.polygons=polygons;
 for(const f of polygons){
  ctx.beginPath();f.p.forEach((p,j)=>j?ctx.lineTo(p[0],p[1]):ctx.moveTo(p[0],p[1]));ctx.closePath();
  const picked=f.i===selected||(selectedGroup&&f.i>=selectedGroup[0]&&f.i<selectedGroup[1]);
  if(surface){ctx.fillStyle=picked?'#f4be50':f.color;ctx.fill();}
  if(wire||picked){ctx.strokeStyle=picked?'#fff4bc':'#171a35';
    ctx.lineWidth=picked?3:1.35;ctx.stroke()}
  if(labels){const x=f.p.reduce((a,v)=>a+v[0],0)/f.p.length;
   const y=f.p.reduce((a,v)=>a+v[1],0)/f.p.length;
   ctx.font='bold '+Math.max(11,Math.round(Math.min(w,h)/75))+'px sans-serif';
   ctx.textAlign='center';ctx.textBaseline='middle';ctx.lineWidth=3;
   ctx.strokeStyle='#000';ctx.strokeText(String(f.id),x,y);
   ctx.fillStyle='#fff';ctx.fillText(String(f.id),x,y)}
 }
}
function inside(poly,x,y){let ok=false;for(let i=0,j=poly.length-1;i<poly.length;j=i++){
 const a=poly[i],b=poly[j];if(((a[1]>y)!==(b[1]>y))&&x<(b[0]-a[0])*(y-a[1])/(b[1]-a[1])+a[0])ok=!ok}return ok}
cv.addEventListener('pointerdown',e=>{drag={x:e.clientX,y:e.clientY,moved:false};cv.setPointerCapture(e.pointerId)});
cv.addEventListener('pointermove',e=>{if(!drag)return;const dx=e.clientX-drag.x,dy=e.clientY-drag.y;
 if(Math.abs(dx)+Math.abs(dy)>1)drag.moved=true;
 if(drag.moved){yaw+=dx*.009;pitch=Math.max(-1.45,Math.min(1.45,pitch+dy*.009));draw()}
 drag.x=e.clientX;drag.y=e.clientY});
cv.addEventListener('pointerup',e=>{if(!drag)return;const moved=drag.moved;drag=null;if(moved)return;
 const r=cv.getBoundingClientRect(),x=(e.clientX-r.left)*cv.width/r.width,y=(e.clientY-r.top)*cv.height/r.height;
 const hit=[...(window.polygons||[])].reverse().find(f=>inside(f.p,x,y));
 if(hit&&bridge)bridge.selectFace(hit.i)});
cv.addEventListener('wheel',e=>{e.preventDefault();zoom=Math.max(.6,Math.min(8,zoom*(e.deltaY>0?.9:1.1)));draw()},{passive:false});
// Flechas verticales: desplazar en el eje vertical de la pantalla, segun camara.
function selectFaceInDirection(key){
  if(!mesh||!bridge||!(window.polygons||[]).length)return;
  const faces=window.polygons;
  const center=f=>[
    f.p.reduce((sum,p)=>sum+p[0],0)/f.p.length,
    f.p.reduce((sum,p)=>sum+p[1],0)/f.p.length
  ];
  const axis=key==='ArrowLeft'?[-1,0]:key==='ArrowRight'?[1,0]:
    key==='ArrowUp'?[0,-1]:[0,1];
  const current=[...faces].reverse().find(f=>f.i===selected);
  if(!current)return;
  const origin=center(current);
  // Elegir caras de acuerdo con su posicion VISUAL; nunca avanzar por ID.
  // El orden de dibujo es de atras hacia delante: identificar la cara visible
  // en el centro de cada candidata evita navegar hacia caras ocultas.
  function visible(f){
    const c=center(f);
    for(let i=faces.length-1;i>=0;i--){
      const top=faces[i];
      if(inside(top.p,c[0],c[1]))return top===f;
    }
    return false;
  }
  const candidates=[];
  for(const f of faces){
    if(f.i===selected||!visible(f))continue;
    const c=center(f),dx=c[0]-origin[0],dy=c[1]-origin[1];
    const along=dx*axis[0]+dy*axis[1];
    const across=Math.abs(dx*axis[1]-dy*axis[0]);
    if(along<=4||across>along*1.8)continue;
    const shared=mesh.faces[selected]?.filter(v=>mesh.faces[f.i]?.includes(v)).length||0;
    // Cara vecina primero; si no hay, siguiente lugar visible en esa direccion.
    const distance=Math.hypot(dx,dy);
    const score=distance+across*1.4-(shared>=2?10000:shared===1?1500:0);
    candidates.push({f,score});
  }
  candidates.sort((a,b)=>a.score-b.score);
  if(candidates.length)bridge.selectFace(candidates[0].f.i);
}
window.addEventListener('keydown',e=>{
  const target=e.target;
  if(target&&['INPUT','TEXTAREA','SELECT'].includes(target.tagName))return;
  if(e.altKey&&['ArrowUp','ArrowDown','ArrowLeft','ArrowRight'].includes(e.key)){
    e.preventDefault();selectFaceInDirection(e.key);return;
  }
  if(!['ArrowUp','ArrowDown','ArrowLeft','ArrowRight'].includes(e.key))return;
  if(e.altKey||e.metaKey)return;
  e.preventDefault();
  if(!e.ctrlKey){
    const turn=e.shiftKey?Math.PI/120:Math.PI/24;
    if(e.key==='ArrowLeft')yaw-=turn;
    if(e.key==='ArrowRight')yaw+=turn;
    if(e.key==='ArrowUp')pitch=Math.min(1.45,pitch+turn);
    if(e.key==='ArrowDown')pitch=Math.max(-1.45,pitch-turn);
    draw();return;
  }
  if(!bridge||!mesh)return;
  const step=e.shiftKey?.005:.025;
  if(e.key==='ArrowLeft'||e.key==='ArrowRight'){
    const dir=e.key==='ArrowRight'?1:-1;
    // Eje horizontal de la pantalla, segun la rotacion de la camara.
    bridge.movePerspective(dir*step*Math.cos(yaw),0,dir*step*Math.sin(yaw));
  }else{
    const dir=e.key==='ArrowUp'?1:-1;
    // Eje vertical de la pantalla, respetando yaw y pitch.
    bridge.movePerspective(
      dir*step*Math.sin(yaw)*Math.sin(pitch),
      dir*step*Math.cos(pitch),
      -dir*step*Math.cos(yaw)*Math.sin(pitch));
  }
});
setInterval(()=>{if(spin){yaw+=.0035;draw()}},33);
resize();
</script></body></html>
"""

class Bridge(QObject):
    def __init__(self, editor):
        super().__init__()
        self.editor = editor

    @Slot(int)
    def selectFace(self, index):
        self.editor.select_face(index)

    @Slot(int)
    def selectAdjacentPiece(self, direction):
        self.editor.select_adjacent_piece(direction)

    @Slot(float, float, float)
    def movePerspective(self, dx, dy, dz):
        self.editor.move_perspective(dx, dy, dz)


class ExpandableSection(QWidget):
    def __init__(self, title, expanded=True):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.toggle = QToolButton()
        self.toggle.setText(title)
        self.toggle.setCheckable(True)
        self.toggle.setChecked(expanded)
        self.toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.toggle.setArrowType(Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow)
        self.toggle.setStyleSheet("QToolButton{text-align:left;padding:10px;background:#202b47;border:1px solid #3b4b75;border-radius:7px;color:#dceaff;font-weight:bold}")
        layout.addWidget(self.toggle)
        self.content = QWidget()
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(9, 7, 9, 9)
        layout.addWidget(self.content)
        self.content.setVisible(expanded)
        self.toggle.toggled.connect(self._changed)

    def _changed(self, checked):
        self.content.setVisible(checked)
        self.toggle.setArrowType(Qt.ArrowType.DownArrow if checked else Qt.ArrowType.RightArrow)


class Editor(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"PYRION EDIT v{APP_VERSION} · Modelador Origami")
        self.resize(1390, 830)
        self.mesh = None
        self.path = None
        self.saved = None
        self.remote_sha = None
        self.selection = []
        self.selecting = False
        self.view = QWebEngineView()
        self.channel = QWebChannel(self.view.page())
        self.bridge = Bridge(self)
        self.channel.registerObject("bridge", self.bridge)
        self.view.page().setWebChannel(self.channel)
        self.view.setHtml(HTML, "qrc:///")
        self.view.loadFinished.connect(lambda ok: self.push_mesh() if ok else None)
        self.make_ui()
        self.setStyleSheet("""
          QMainWindow,QWidget{background:#101424;color:#e7e9ff;font-size:13px}
          QPushButton,QComboBox,QDoubleSpinBox{background:#222942;border:1px solid #3b4b75;
            border-radius:6px;padding:8px;color:#fff}
          QPushButton:hover{background:#365187}
          QGroupBox{border:1px solid #384260;border-radius:8px;margin-top:14px;padding:10px;font-weight:bold}
          QGroupBox::title{subcontrol-origin:margin;left:12px;padding:0 6px}
          QCheckBox{spacing:8px}""")
        self.load_remote()

    def make_ui(self):
        root = QWidget()
        row = QHBoxLayout(root)
        row.setContentsMargins(0, 0, 0, 0)
        panel = QWidget()
        panel.setFixedWidth(330)
        outer = QVBoxLayout(panel)
        outer.setContentsMargins(6, 6, 6, 6)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        body = QWidget()
        left = QVBoxLayout(body)
        left.setContentsMargins(3, 3, 3, 3)
        scroll.setWidget(body)
        outer.addWidget(scroll)
        heading = QLabel("PYRION 3D  /  EDIT")
        heading.setStyleSheet("font-size:21px;font-weight:bold;color:#84baff;padding:12px")
        left.addWidget(heading)
        files_section = ExpandableSection("Archivos y GitHub", False)
        left.addWidget(files_section)
        for label, fn in [("Abrir .mesh", self.open_file), ("Cargar CHEST de GitHub", self.load_remote),
                          ("Guardar .mesh", self.save_file), ("Guardar como...", self.save_as),
                          ("Guardar en GitHub", self.save_github)]:
            b = QPushButton(label)
            b.clicked.connect(fn)
            files_section.content_layout.addWidget(b)
        group = QGroupBox("Seleccionar objeto / cara")
        g = QVBoxLayout(group)
        self.selector = QComboBox()
        self.selector.currentIndexChanged.connect(self.selection_changed)
        g.addWidget(self.selector)
        self.selection_info = QLabel("Seleccione una pieza o cara")
        self.selection_info.setWordWrap(True)
        g.addWidget(self.selection_info)
        group_section = ExpandableSection("Seleccionar objeto o cara", False)
        group_section.content_layout.addWidget(group)
        left.addWidget(group_section)
        trans = QGroupBox("Mover seleccion por valores X / Y / Z")
        form = QFormLayout(trans)
        self.spins = []
        for axis in "XYZ":
            v = QDoubleSpinBox()
            v.setDecimals(5);v.setRange(-10000, 10000);v.setSingleStep(0.01)
            v.valueChanged.connect(self.apply_coordinates)
            form.addRow(axis + ":", v)
            self.spins.append(v)
        self.note = QLabel("Desplazamiento relativo al seleccionar.\nFlechas ↑ ↓ ← →: girar cámara.\nCtrl+flechas: mover pieza según vista.\nShift: precisión.\nAlt+flechas: seleccionar cara segun vista.\nLas caras comparten vértices.")
        self.note.setWordWrap(True)
        form.addRow(self.note)
        btn = QPushButton("Restablecer desplazamiento de selección")
        btn.clicked.connect(self.reset_transform)
        form.addRow(btn)
        move_section = ExpandableSection("Mover X / Y / Z", False)
        move_section.content_layout.addWidget(trans)
        left.addWidget(move_section)
        opts = QGroupBox("Visualización")
        op = QVBoxLayout(opts)
        self.toggles = {}
        for key, title, value in [("mirror","Espejo X",True),("wire","Aristas reales",True),
                                  ("material","Con material (colores)",True),("surface","Mostrar superficie",True),
                                  ("labels","Números de caras",True),
                                  ("spin","Giro automático",False)]:
            cb = QCheckBox(title);cb.setChecked(value);cb.toggled.connect(self.push_options)
            self.toggles[key]=cb;op.addWidget(cb)
        options_section = ExpandableSection("Visualizacion", False)
        options_section.content_layout.addWidget(opts)
        left.addWidget(options_section)
        self.status = QLabel("")
        self.status.setWordWrap(True)
        left.addWidget(self.status)
        left.addStretch()
        row.addWidget(panel)
        row.addWidget(self.view,1)
        self.setCentralWidget(root)

    def js(self, script):
        self.view.page().runJavaScript(script)

    def push_mesh(self):
        if self.mesh:
            self.js("setMesh(" + json.dumps(self.mesh,ensure_ascii=False) + ");")
            self.push_options()

    def push_options(self):
        self.js("setOptions(" + json.dumps({k:v.isChecked() for k,v in self.toggles.items()}) + ");")

    def set_mesh(self, model, path=None):
        if model.get("format")!="pyrion.mesh" or not isinstance(model.get("vertices"),list) or not isinstance(model.get("faces"),list):
            raise ValueError("Formato .mesh no compatible")
        self.mesh=deepcopy(model);self.path=path;self.saved=deepcopy(model)
        self.remote_sha = None
        self.populate();self.push_mesh()
        self.status.setText("Modelo cargado: " + str(model.get("name","sin nombre")) +
                            " · v" + str(model.get("version","?")) + " · " + str(len(model["faces"])) + " caras")

    def populate(self):
        self.selecting=True;self.selector.clear()
        for i,g in enumerate(self.mesh.get("groups",[])):
            self.selector.addItem("▣ "+g.get("name","Grupo "+str(i)),("group",i))
        for i,f in enumerate(self.mesh["faces"]):
            number=(self.mesh.get("face_ids") or list(range(1,len(self.mesh["faces"])+1)))[i]
            self.selector.addItem("□ Cara "+str(number)+" ("+str(len(f))+" vértices)",("face",i))
        self.selecting=False
        if self.selector.count():self.selector.setCurrentIndex(0);self.selection_changed()

    def vertex_ids(self,kind,index):
        if kind=="face":return sorted(set(self.mesh["faces"][index]))
        g=self.mesh["groups"][index]
        first=int(g.get("face_start",0));last=first+int(g.get("face_count",0))
        return sorted({v for f in self.mesh["faces"][first:last] for v in f})

    def selection_changed(self,*_):
        if self.selecting or self.mesh is None:return
        item=self.selector.currentData()
        if item is None:return
        kind,i=item
        self.selection=self.vertex_ids(kind,i)
        self.anchor={j:list(self.mesh["vertices"][j]) for j in self.selection}
        self.selecting=True
        for spin in self.spins:spin.setValue(0)
        self.selecting=False
        self.selection_info.setText(str(len(self.selection))+" vértices seleccionados · " +
            ("pieza completa" if kind=="group" else "cara editable"))
        if kind=="face":
            self.js("setSelected("+str(i)+");")
        else:
            group=self.mesh["groups"][i]
            a=int(group.get("face_start",0));b=a+int(group.get("face_count",0))
            self.js(f"setSelectedGroup({a},{b});")

    def select_adjacent_piece(self, direction):
        if not self.mesh or not self.mesh.get("faces"):
            return
        ids = self.mesh.get("face_ids") or list(range(1, len(self.mesh["faces"])+1))
        ordered = sorted((face_id, index) for index, face_id in enumerate(ids))
        current = self.selector.currentData()
        if current and current[0] == "face":
            current_id = ids[current[1]]
            pos = next((i for i, (fid, _) in enumerate(ordered) if fid == current_id), 0)
            pos = (pos + (1 if direction > 0 else -1)) % len(ordered)
        else:
            pos = 0 if direction > 0 else len(ordered)-1
        face_index = ordered[pos][1]
        self.select_face(face_index)

    def select_face(self,i):
        for j in range(self.selector.count()):
            if self.selector.itemData(j)==("face",i):
                self.selector.setCurrentIndex(j);break

    def apply_coordinates(self,*_):
        if self.selecting or not self.mesh or not self.selection:return
        offsets=[spin.value() for spin in self.spins]
        for index in self.selection:
            self.mesh["vertices"][index]=[self.anchor[index][k]+offsets[k] for k in range(3)]
        self.push_mesh()

    def move_perspective(self, dx, dy, dz):
        if not self.mesh or not self.selection:
            return
        self.selecting = True
        try:
            for spin, delta in zip(self.spins, (dx, dy, dz)):
                spin.setValue(round(spin.value() + delta, 5))
        finally:
            self.selecting = False
        self.apply_coordinates()

    def reset_transform(self):
        if not self.mesh:return
        for s in self.spins:s.setValue(0)

    def open_file(self):
        p,_=QFileDialog.getOpenFileName(self,"Abrir malla","","Mallas PYRION (*.mesh);;JSON (*.json)")
        if not p:return
        try:self.set_mesh(json.loads(Path(p).read_text(encoding="utf-8")),p)
        except Exception as ex:QMessageBox.critical(self,"Error al abrir",str(ex))

    def load_remote(self):
        # RAW no consume la cuota de la API publica y es suficiente para abrir modelos.
        # La escritura sigue verificando el SHA con un token de GitHub.
        urls = [
            "https://raw.githubusercontent.com/" + REPO + "/main/" + REMOTE,
            "https://cdn.jsdelivr.net/gh/" + REPO + "@main/" + REMOTE,
        ]
        errors = []
        for url in urls:
            try:
                request = urllib.request.Request(
                    url + "?refresh=" + str(__import__("time").time_ns()),
                    headers={"User-Agent": "PYRION-EDIT/1.2.1", "Cache-Control": "no-cache"})
                with urllib.request.urlopen(request, timeout=18) as response:
                    data = json.loads(response.read().decode("utf-8"))
                self.set_mesh(data)
                self.remote_sha = None
                self.status.setText("CHEST v" + str(data.get("version", "?")) +
                    " cargado desde GitHub RAW. Guardar en GitHub solicitará comprobación autenticada.")
                return
            except Exception as exc:
                errors.append(str(exc))
        self.status.setText("No se pudo descargar CHEST: " +
            " | ".join(errors)[:240] + " · También puede abrir un .mesh local.")

    def save_github(self):
        if not self.mesh:
            QMessageBox.warning(self, "PYRION EDIT", "Primero abra una malla.")
            return
        if self.mesh == self.saved:
            QMessageBox.information(self, "PYRION EDIT", "No hay cambios para publicar.")
            return
        token = os.environ.get("PYRION_GITHUB_TOKEN", "").strip()
        if not token:
            token, accepted = QInputDialog.getText(self, "Autorizacion GitHub",
                "Token de GitHub con permiso Contents: Read and write sobre el repositorio:", QLineEdit.EchoMode.Password)
            if not accepted or not token.strip():
                return
            token = token.strip()
        api = "https://api.github.com/repos/" + REPO + "/contents/" + REMOTE
        headers = {
            "Authorization": "Bearer " + token,
            "Accept": "application/vnd.github+json",
            "User-Agent": "PYRION-EDIT",
            "X-GitHub-Api-Version": "2022-11-28"
        }
        try:
            request = urllib.request.Request(api + "?ref=main", headers=headers)
            with urllib.request.urlopen(request, timeout=20) as response:
                remote = json.load(response)
            if self.remote_sha and remote.get("sha") != self.remote_sha:
                raise RuntimeError("CHEST cambió en GitHub desde que fue abierto. Vuelva a cargarlo antes de publicar.")
            if self.saved is None or remote.get("encoding") != "base64":
                raise RuntimeError("No se pudo verificar la malla remota antes de publicar.")
            remote_mesh = json.loads(base64.b64decode(remote["content"]).decode("utf-8"))
            if remote_mesh != self.saved:
                raise RuntimeError("CHEST cambió en GitHub desde la carga. Recargue antes de publicar.")
            updated = deepcopy(self.mesh)
            original = str(updated.get("version", "1.0.0")).split(".")
            if not original or not all(p.isdecimal() for p in original):
                raise ValueError("La version actual no es numerica.")
            original[-1] = str(int(original[-1]) + 1)
            updated["version"] = ".".join(original)
            answer = QMessageBox.question(self, "Publicar en GitHub",
                "¿Publicar CHEST v" + updated["version"] + " en la rama main?\n"
                "Se reemplazara la malla remota con los cambios actuales.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if answer != QMessageBox.StandardButton.Yes:
                return
            payload = {
                "message": "PYRION EDIT: actualizar CHEST v" + updated["version"],
                "content": base64.b64encode((json.dumps(updated, ensure_ascii=False, indent=2) + "\n").encode("utf-8")).decode("ascii"),
                "sha": remote["sha"],
                "branch": "main"
            }
            put = urllib.request.Request(api, data=json.dumps(payload).encode("utf-8"),
                headers={**headers, "Content-Type": "application/json"}, method="PUT")
            with urllib.request.urlopen(put, timeout=30) as response:
                result = json.load(response)
            self.mesh = updated
            self.saved = deepcopy(updated)
            self.remote_sha = result["content"]["sha"]
            self.status.setText("Publicado CHEST v" + updated["version"] +
                " · commit " + result["commit"]["sha"][:10])
            QMessageBox.information(self, "PYRION EDIT",
                "Guardado en GitHub correctamente.\nCHEST v" + updated["version"])
        except urllib.error.HTTPError as ex:
            detail = ex.read().decode("utf-8", errors="replace")[:350]
            QMessageBox.critical(self, "GitHub", "HTTP " + str(ex.code) + ": " + detail)
        except Exception as ex:
            QMessageBox.critical(self, "GitHub", str(ex))

    def save_file(self):
        if not self.path:return self.save_as()
        try:
            Path(self.path).write_text(json.dumps(self.mesh,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
            self.saved=deepcopy(self.mesh)
            self.status.setText("Guardado: "+self.path)
        except Exception as ex:QMessageBox.critical(self,"Error al guardar",str(ex))

    def save_as(self):
        p,_=QFileDialog.getSaveFileName(self,"Guardar malla",self.path or "chest_edit.mesh","Mallas PYRION (*.mesh)")
        if p:self.path=p;self.save_file()


if __name__=="__main__":
    app=QApplication(sys.argv)
    editor=Editor();editor.showMaximized()
    sys.exit(app.exec())
