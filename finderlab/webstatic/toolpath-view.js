import * as THREE from './vendor/three/three.module.min.js';
import {OrbitControls} from './vendor/three/OrbitControls.js';

// Reusable scene: accepts interpreted geometry, never file paths or printer APIs.
export class ToolpathView {
    constructor(container) {
        this.container = container;
        this.scene = new THREE.Scene(); this.scene.background = new THREE.Color(0x101916);
        this.camera = new THREE.PerspectiveCamera(45, 1, 0.01, 1000000);
        this.camera.up.set(0, 0, 1);
        this.renderer = new THREE.WebGLRenderer({antialias: true, alpha: false});
        this.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
        container.append(this.renderer.domElement);
        this.controls = new OrbitControls(this.camera, this.renderer.domElement);
        this.controls.enableDamping = false; // Render on demand, not a permanent animation loop.
        this.controls.addEventListener('change', () => this.render());
        const grid = new THREE.GridHelper(140, 14, 0x8ca47c, 0x344637);
        grid.rotation.x = Math.PI / 2; this.scene.add(grid);
        this.scene.add(new THREE.AxesHelper(15));
        this.paths = []; this.maximum = Infinity; this.showTravel = false;
        this.observer = new ResizeObserver(() => this.resize()); this.observer.observe(container);
        this.reset(); this.resize();
        this.renderer.domElement.addEventListener('webglcontextlost', event => {
            event.preventDefault(); container.dispatchEvent(new Event('preview-context-lost'));
        });
    }
    resize() {
        const width = Math.max(1, this.container.clientWidth), height = 380;
        this.renderer.setSize(width, height, false); this.camera.aspect = width / height;
        this.camera.updateProjectionMatrix(); this.render();
    }
    clear() {
        for (const path of this.paths) {
            this.scene.remove(path); path.geometry.dispose(); path.material.dispose();
        }
        this.paths = []; this.bounds = null; this.render();
    }
    setToolpath(data) {
        this.clear();
        const colours = [0xc6e995, 0x628aaf, 0xed80cf];
        for (let kind = 0; kind < 3; kind++) {
            const count = data.counts[['extrusion', 'travel', 'unknown'][kind]];
            if (!count) continue;
            const positions = new Float32Array(count * 6), heights = new Float32Array(count * 2);
            let index = 0;
            for (let i = 0; i < data.kinds.length; i++) {
                if (data.kinds[i] !== kind) continue;
                positions.set(data.positions.subarray(i * 6, i * 6 + 6), index * 6);
                heights[index * 2] = heights[index * 2 + 1] = data.heights[i]; index++;
            }
            const geometry = new THREE.BufferGeometry();
            geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
            geometry.setAttribute('segmentHeight', new THREE.BufferAttribute(heights, 1));
            const material = new THREE.ShaderMaterial({
                uniforms: {maximumHeight: {value: 1e9}, colour: {value: new THREE.Color(colours[kind])}},
                vertexShader: `attribute float segmentHeight; varying float height;
                    void main(){height=segmentHeight; gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.0);}`,
                fragmentShader: `uniform float maximumHeight; uniform vec3 colour; varying float height;
                    void main(){if(height>maximumHeight+0.0001) discard; gl_FragColor=vec4(colour,1.0);}`
            });
            const path = new THREE.LineSegments(geometry, material); path.userData.kind = kind;
            // No clipping of segments that cross the selected height: hide whole segment.
            path.frustumCulled = false; this.paths.push(path); this.scene.add(path);
        }
        const primary = this.paths.find(p => p.userData.kind === 0) || this.paths.find(p => p.userData.kind === 2) || this.paths[0];
        primary.geometry.computeBoundingBox(); this.bounds = primary.geometry.boundingBox.clone();
        this.filter(Infinity, false); this.reset();
    }
    setModel(data) {
        this.clear();
        const geometry = new THREE.BufferGeometry();
        geometry.setAttribute('position', new THREE.BufferAttribute(data.positions, 3));
        geometry.setAttribute('normal', new THREE.BufferAttribute(data.normals, 3));
        geometry.computeBoundingBox();
        const center = geometry.boundingBox.getCenter(new THREE.Vector3());
        const mesh = new THREE.Mesh(geometry, new THREE.MeshNormalMaterial({side: THREE.DoubleSide}));
        // Display-only placement, not a model transform exported to the slicer.
        mesh.position.set(-center.x, -center.y, -geometry.boundingBox.min.z);
        mesh.userData.kind = 'model'; this.paths.push(mesh); this.scene.add(mesh);
        this.bounds = geometry.boundingBox.clone().translate(mesh.position); this.reset();
    }
    wireframe(enabled) {
        for (const path of this.paths) if (path.userData.kind === 'model') path.material.wireframe = enabled;
        this.render();
    }
    filter(height, showTravel) {
        this.maximum = height; this.showTravel = showTravel;
        for (const path of this.paths) {
            if (path.userData.kind === 'model') continue;
            path.visible = path.userData.kind !== 1 || showTravel;
            path.material.uniforms.maximumHeight.value = Number.isFinite(height) ? height : 1e9;
        }
        this.render();
    }
    reset() {
        const center = this.bounds ? this.bounds.getCenter(new THREE.Vector3()) : new THREE.Vector3(0, 0, 10);
        const size = this.bounds ? Math.max(20, this.bounds.getSize(new THREE.Vector3()).length()) : 160;
        this.camera.position.copy(center).add(new THREE.Vector3(size, -size, size));
        this.camera.near = Math.max(.01, size / 10000); this.camera.far = Math.max(1000, size * 20);
        this.camera.updateProjectionMatrix(); this.controls.target.copy(center); this.controls.update(); this.render();
    }
    render() { this.renderer.render(this.scene, this.camera); }
}
