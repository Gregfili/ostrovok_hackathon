import { useEffect, useRef, useState } from 'react'
import * as THREE from 'three'
import { OrbitControls } from 'three/addons/controls/OrbitControls.js'

const HEIGHT = 5

function eyeHeight(scene, floor) {
  return (floor - 1) * scene.floor_m + scene.eye_m
}

function rayEnd(scene, floor) {
  const y = eyeHeight(scene, floor)
  const [tx, tbase, tz, theight] = scene.target
  const top = tbase + theight
  const total = Math.hypot(tx, tz) || 1
  for (const blocker of scene.blockers || []) {
    const sight = y + (top - y) * (blocker.distance / total)
    if (blocker.roof > sight + 0.3) {
      return { x: blocker.x, y: blocker.roof, z: blocker.z, blocked: true }
    }
  }
  return { x: tx, y: top, z: tz, blocked: false }
}

function placeRay(mesh, fromY, end) {
  const start = new THREE.Vector3(0, fromY * HEIGHT, 0)
  const finish = new THREE.Vector3(end.x, end.y * HEIGHT, end.z)
  const direction = finish.clone().sub(start)
  const length = Math.max(direction.length(), 1)
  mesh.scale.set(1, length, 1)
  mesh.position.copy(start).add(finish).multiplyScalar(0.5)
  mesh.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), direction.normalize())
  mesh.material.color.set(end.blocked ? '#a33b24' : '#1f4d3a')
}

export default function CathedralView({ scene, sentence, check, passport }) {
  const mountRef = useRef(null)
  const lineRef = useRef(null)
  const eyeRef = useRef(null)
  const [floor, setFloor] = useState(scene.open_floor || 1)

  useEffect(() => {
    const mount = mountRef.current
    if (!mount || !scene?.terrain) return undefined
    const width = mount.clientWidth || 320
    const height = mount.clientHeight || 280
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true })
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2))
    renderer.setSize(width, height)
    mount.appendChild(renderer.domElement)

    const view = new THREE.Scene()
    view.background = new THREE.Color('#e7efe8')
    view.add(new THREE.AmbientLight('#fff6e8', 0.85))
    const sun = new THREE.DirectionalLight('#fff1d0', 1.35)
    sun.position.set(-600, 900, 400)
    view.add(sun)

    const { terrain } = scene
    const positions = []
    const indices = []
    for (let row = 0; row < terrain.rows; row += 1) {
      for (let col = 0; col < terrain.cols; col += 1) {
        const x = terrain.origin[0] + col * terrain.step[0]
        const z = terrain.origin[1] + row * terrain.step[1]
        const y = terrain.heights[row * terrain.cols + col] * HEIGHT
        positions.push(x, y, z)
      }
    }
    for (let row = 0; row < terrain.rows - 1; row += 1) {
      for (let col = 0; col < terrain.cols - 1; col += 1) {
        const a = row * terrain.cols + col
        indices.push(a, a + 1, a + terrain.cols, a + 1, a + terrain.cols + 1, a + terrain.cols)
      }
    }
    const ground = new THREE.BufferGeometry()
    ground.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3))
    ground.setIndex(indices)
    ground.computeVertexNormals()
    view.add(new THREE.Mesh(ground, new THREE.MeshLambertMaterial({ color: '#b7c9b0' })))

    const buildings = []
    for (const building of scene.buildings || []) {
      const ring = building.ring || []
      if (ring.length < 3) continue
      const shape = new THREE.Shape(ring.map(([x, z]) => new THREE.Vector2(x, -z)))
      const geometry = new THREE.ExtrudeGeometry(shape, { depth: building.height * HEIGHT, bevelEnabled: false })
      geometry.rotateX(-Math.PI / 2)
      const mesh = new THREE.Mesh(
        geometry,
        new THREE.MeshLambertMaterial({ color: building.blocks ? '#b86a45' : '#d9d3c7' }),
      )
      mesh.position.y = building.base * HEIGHT
      view.add(mesh)
      buildings.push(geometry)
    }

    const [tx, tbase, tz, theight] = scene.target
    const cathedral = new THREE.Mesh(
      new THREE.BoxGeometry(140, theight * HEIGHT, 140),
      new THREE.MeshLambertMaterial({ color: '#c4a35a' }),
    )
    cathedral.position.set(tx, (tbase + theight / 2) * HEIGHT, tz)
    view.add(cathedral)
    const dome = new THREE.Mesh(
      new THREE.SphereGeometry(48, 24, 16),
      new THREE.MeshLambertMaterial({ color: '#e6d7a8' }),
    )
    dome.position.set(tx, (tbase + theight) * HEIGHT + 24, tz)
    view.add(dome)

    const toward = new THREE.Vector2(tx, tz)
    if (toward.lengthSq() > 1) toward.normalize()
    const hotelHeight = (scene.levels || 7) * scene.floor_m * HEIGHT
    const hotel = new THREE.Mesh(
      new THREE.BoxGeometry(36, hotelHeight, 22),
      new THREE.MeshLambertMaterial({ color: '#1f4d3a' }),
    )
    hotel.position.set(-toward.x * 28, hotelHeight / 2, -toward.y * 28)
    view.add(hotel)

    const line = new THREE.Mesh(
      new THREE.CylinderGeometry(7, 7, 1, 8),
      new THREE.MeshBasicMaterial({ color: '#1f4d3a' }),
    )
    view.add(line)
    lineRef.current = line
    const eye = new THREE.Mesh(
      new THREE.SphereGeometry(8, 16, 12),
      new THREE.MeshBasicMaterial({ color: '#1f4d3a' }),
    )
    view.add(eye)
    eyeRef.current = eye

    const look = new THREE.Vector3(tx, (tbase + theight) * HEIGHT, tz)
    const eyeY = eyeHeight(scene, scene.open_floor || 1) * HEIGHT
    const camera = new THREE.PerspectiveCamera(48, width / height, 1, 20000)
    camera.position.set(-toward.x * 90, eyeY + 70, -toward.y * 90)
    const controls = new OrbitControls(camera, renderer.domElement)
    controls.target.copy(look)
    controls.minDistance = 20
    controls.maxDistance = 9000
    controls.update()

    let frame = 0
    const draw = () => {
      frame = requestAnimationFrame(draw)
      controls.update()
      renderer.render(view, camera)
    }
    draw()

    const onResize = () => {
      const nextWidth = mount.clientWidth || width
      const nextHeight = mount.clientHeight || height
      camera.aspect = nextWidth / nextHeight
      camera.updateProjectionMatrix()
      renderer.setSize(nextWidth, nextHeight)
    }
    window.addEventListener('resize', onResize)
    return () => {
      cancelAnimationFrame(frame)
      window.removeEventListener('resize', onResize)
      controls.dispose()
      ground.dispose()
      buildings.forEach((geometry) => geometry.dispose())
      cathedral.geometry.dispose()
      dome.geometry.dispose()
      hotel.geometry.dispose()
      line.geometry.dispose()
      eye.geometry.dispose()
      renderer.dispose()
      mount.removeChild(renderer.domElement)
      lineRef.current = null
      eyeRef.current = null
    }
  }, [scene])

  useEffect(() => {
    const line = lineRef.current
    const eye = eyeRef.current
    if (!line || !eye || !scene?.target) return
    const y = eyeHeight(scene, floor)
    placeRay(line, y, rayEnd(scene, floor))
    eye.position.set(0, y * HEIGHT, 0)
  }, [floor, scene])

  const open = !rayEnd(scene, floor).blocked
  return (
    <div
      className="mt-3"
      onClick={(event) => event.stopPropagation()}
      onPointerDown={(event) => event.stopPropagation()}
    >
      <p className="text-sm font-medium">Вид на храм</p>
      <p className="text-sm">{sentence}</p>
      {passport && <p className="text-sm text-mute">{passport}</p>}
      {check && <p className="text-sm text-mute">{check}</p>}
      <div ref={mountRef} className="mt-2 h-72 w-full overflow-hidden rounded-xl bg-[#e7efe8]" />
      <label className="mt-2 flex items-center gap-3 text-sm">
        <span className="shrink-0">{floor}-й этаж</span>
        <input
          type="range"
          min={1}
          max={scene.levels || 7}
          value={floor}
          onChange={(event) => setFloor(Number(event.target.value))}
          className="w-full accent-pine"
        />
      </label>
      <p className="text-sm text-mute">
        {open
          ? 'С этого этажа луч до купола проходит над домами и рельефом.'
          : 'С этого этажа луч ещё упирается в дом по пути.'}
      </p>
      <p className="text-sm text-mute">
        Зелёный корпус — {scene.hotel || 'отель'}, терракотовые — дома на луче, золотой — храм. Высоты увеличены, иначе луч на два километра не разглядеть. Крутите схему мышью.
      </p>
    </div>
  )
}
