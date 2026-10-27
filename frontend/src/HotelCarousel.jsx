import { useEffect, useRef, useState } from 'react'

const SLIDES = [
  { src: '/media/pictures/karusel/grand_hotel.jpg', alt: 'Grand Hotel' },
  { src: '/media/pictures/karusel/hotel1.jpg', alt: 'Отель 1' },
  { src: '/media/pictures/karusel/super_hotel.jpg', alt: 'Super Hotel' },
  { src: '/media/pictures/karusel/hotel2.jpg', alt: 'Отель 2' },
  { src: '/media/pictures/karusel/Grand_Hotel_Europe_fragm.jpg', alt: 'Grand Hotel Europe' },
  { src: '/media/pictures/karusel/hotel3.jpg', alt: 'Отель 3' },
  { src: '/media/pictures/karusel/hotel4.jpg', alt: 'Отель 4' },
]

export const CAROUSEL_REGIONS = [
  'Москва',
  'Санкт-Петербург',
  'Московская область',
  'Краснодарский край',
  'Республика Татарстан',
  'Сверdловская область',
  'Новосибирская область',
  'Красноярский край',
  'Приморский край',
  'Ростовская область',
]

const TICK_MS = 3800
const SHIFT_MS = 700
/** В ряду одновременно 5 кадров: diff −2 … +2 */
const VISIBLE_RADIUS = 2

function wrapDiff(index, active, total) {
  let diff = index - active
  while (diff > total / 2) diff -= total
  while (diff < -total / 2) diff += total
  return diff
}

function slotStyle(diff) {
  const distance = Math.abs(diff)
  const center = diff === 0
  return {
    width: center ? '10.75rem' : `${9.25 - distance * 0.625}rem`,
    height: center ? '10.75rem' : `${12.75 - distance * 1.05}rem`,
    transform: `translateY(${center ? -10 : distance * 2}px) scale(${center ? 1.08 : 1 - distance * 0.045})`,
    zIndex: 20 - distance,
  }
}

function shiftLabel(direction) {
  return direction === 'left'
    ? 'Карусель сдвигается влево'
    : 'Карусель сдвигается вправо'
}

function ShiftArrowIcon({ direction }) {
  return (
    <svg
      viewBox="0 0 24 24"
      aria-hidden="true"
      className="h-6 w-6 fill-none stroke-current stroke-2 transition-transform duration-300"
    >
      {direction === 'left' ? (
        <path d="M14 6l-6 6 6 6" strokeLinecap="round" strokeLinejoin="round" />
      ) : (
        <path d="M10 6l6 6-6 6" strokeLinecap="round" strokeLinejoin="round" />
      )}
    </svg>
  )
}

/** Плашка у края экрана; inset — отступ от края, когда рядом открыта боковая панель */
export function CarouselShiftIndicator({ direction, edge, onClick, titleExtra, inset = 0 }) {
  const isLeft = edge === 'left'
  const label = shiftLabel(direction)
  const edgeClass = isLeft ? 'rounded-r-2xl' : 'rounded-l-2xl'
  const positionStyle = isLeft ? { left: inset } : { right: inset }
  const className = `fixed top-1/2 z-50 flex -translate-y-1/2 items-center justify-center bg-pine px-3 py-4 text-panel shadow-md ${edgeClass}`
  const title = titleExtra ? `${label}. ${titleExtra}` : label

  if (onClick) {
    return (
      <button
        type="button"
        onClick={onClick}
        className={className}
        style={positionStyle}
        aria-live="polite"
        aria-label={label}
        title={title}
      >
        <ShiftArrowIcon direction={direction} />
      </button>
    )
  }

  return (
    <div
      className={className}
      style={positionStyle}
      aria-live="polite"
      aria-label={label}
      title={title}
    >
      <ShiftArrowIcon direction={direction} />
    </div>
  )
}

export default function HotelCarousel({ onShiftDirection, dock = 'center' }) {
  const [active, setActive] = useState(0)
  const prevActive = useRef(active)
  const total = SLIDES.length
  const dockPx = dock === 'left' ? 44 : dock === 'right' ? -44 : 0

  useEffect(() => {
    if (dock !== 'center') return undefined
    const timer = window.setInterval(() => {
      setActive((current) => (current + 1) % total)
    }, TICK_MS)
    return () => window.clearInterval(timer)
  }, [total, dock])

  useEffect(() => {
    if (prevActive.current === active) return
    onShiftDirection?.('left')
    const settle = window.setTimeout(() => onShiftDirection?.('right'), SHIFT_MS)
    prevActive.current = active
    return () => window.clearTimeout(settle)
  }, [active, onShiftDirection])

  const ordered = SLIDES.map((slide, index) => ({
    ...slide,
    index,
    diff: wrapDiff(index, active, total),
  }))
    .filter((slide) => Math.abs(slide.diff) <= VISIBLE_RADIUS)
    .sort((a, b) => a.diff - b.diff)

  return (
    <div
      className="relative w-full min-h-[11rem] overflow-visible py-2 sm:min-h-[12.5rem] sm:py-3"
      aria-hidden="true"
    >
      <div
        className="absolute bottom-0 left-1/2 flex items-end gap-2 transition-transform duration-500 ease-in-out sm:gap-2.5 md:gap-3"
        style={{ transform: `translate(calc(-50% + ${dockPx}px), 0)` }}
      >
        {ordered.map((slide) => (
          <div
            key={slide.src}
            className="shrink-0 transition-all duration-700 ease-in-out"
            style={slotStyle(slide.diff)}
          >
            <img
              src={slide.src}
              alt={slide.alt}
              className="h-full w-full rounded-2xl object-cover shadow-[0_14px_36px_rgba(0,0,0,0.18)] ring-1 ring-line/80 sm:rounded-3xl"
              loading="lazy"
              decoding="async"
            />
          </div>
        ))}
      </div>
    </div>
  )
}
