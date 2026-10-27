import { useEffect, useState } from 'react'
import Admin from './Admin.jsx'
import HotelCarousel, { CAROUSEL_REGIONS, CarouselShiftIndicator } from './HotelCarousel.jsx'
const GREETING =
  'Планируете поездку? Опишите, какая она должна быть, и мы подберём вам подходящие варианты.'

const QUERY_SAMPLE =
  'Например: мне нужен тихий отель, люблю походить по булгаковским местам, а также шопинг, и вечером развлечься в ночном клубе.'

const NIGHT_KIND = {
  nightclub: 'ночной клуб',
  bar: 'бар',
  pub: 'паб',
  biergarten: 'бирхаус',
  stripclub: 'стриптиз-клуб',
}

function factBy(hotel, feature) {
  return (hotel.facts || []).find((item) => item.feature === feature)
}

function nightLine(side) {
  if (side.night_m == null) return 'ночного заведения ближе 250 м нет'
  const kind = NIGHT_KIND[side.night_kind] || side.night_kind || 'заведение'
  return `${kind} «${side.night_name}», ${side.night_m} м`
}

function HotelPhoto({ hotel, large }) {
  if (!hotel?.image && !hotel?.src) return null
  const src = hotel.image || hotel.src
  const credit = hotel.image_credit || hotel.credit
  return (
    <figure className={large ? 'mb-3' : 'mb-2'}>
      <img
        src={src}
        alt={hotel.name || hotel.title || 'Отель'}
        className={`w-full rounded-xl object-cover ${large ? 'h-64' : 'h-36'}`}
      />
      {credit && <figcaption className="mt-1 text-xs text-mute">{credit}</figcaption>}
    </figure>
  )
}

function CardSheet({ sheet }) {
  return (
    <div>
      {sheet.image && <HotelPhoto hotel={{ ...sheet.image, name: sheet.title }} large />}
      {(sheet.sections || []).map((section) => (
        <section key={section.title} className="mt-4">
          <h3 className="text-sm font-medium">{section.title}</h3>
          <ul className="mt-2 grid gap-1">
            {(section.items || []).map((item) => (
              <li key={`${section.title}-${item.name}`} className="flex justify-between gap-3 text-sm">
                <span>{item.name}</span>
                <span className="shrink-0 text-mute">{item.distance}</span>
              </li>
            ))}
          </ul>
        </section>
      ))}
    </div>
  )
}

function HotelDossier({ hotel, picked, onPick, onChoose }) {
  const noise = factBy(hotel, 'facade_noise')
  const view = factBy(hotel, 'facade_visibility')
  const walk = factBy(hotel, 'walk_to')
  const sides = noise?.data?.sides || []
  const shots = view?.data?.shots || []
  const sunHours = view?.data?.sun_hours || {}
  const question = (hotel.facts || []).find((item) => item.question)?.question
  const quieter = noise?.data?.quieter_label
  return (
    <article
      onClick={onPick}
      className={`w-full cursor-pointer rounded-2xl border px-4 py-3 text-left ${
        picked ? 'border-pine bg-panel' : 'border-line bg-panel/60'
      }`}
    >
      <HotelPhoto hotel={hotel} large={picked} />
      <p className="font-medium">{hotel.name || hotel.id}</p>
      <p className="text-sm text-mute">{hotel.address}</p>
      {sides.length === 0 ? (
        <p className="mt-2 text-sm">Сторон пока нет.</p>
      ) : (
        <ul className="mt-3 grid gap-2">
          {sides.map((side) => {
            const shot = shots.find((item) => item.title === side.title)
            return (
              <li key={side.id || side.title} className="rounded-xl bg-paper px-3 py-2 text-sm">
                <p className="font-medium">{side.title}</p>
                <p>
                  {side.faces_name}, {Math.round(side.faces_distance_m)} м
                </p>
                <p>{nightLine(side)}</p>
                {sunHours[side.title] && <p>{sunHours[side.title]}</p>}
                {shot?.verdict === 'open' && <p>Есть проём.</p>}
              </li>
            )
          })}
        </ul>
      )}
      {noise && (
        <p className="mt-2 text-sm">
          {quieter ? `Тише: ${quieter}.` : 'Какая сторона тише, пока не ясно.'}
        </p>
      )}
      {Number.isFinite(walk?.data?.minutes) && (
        <p className="mt-2 text-sm">{walk.data.minutes} минут пешком</p>
      )}
      {question && <p className="mt-2 text-sm text-moss">Вопрос отелю: {question}</p>}
      {onChoose && (
        <button
          type="button"
          onClick={onChoose}
          className="mt-3 rounded-xl bg-pine px-4 py-2 text-sm text-panel"
        >
          Выбрать
        </button>
      )}
    </article>
  )
}

function GuestGate({ onEnter, onClose }) {
  const [guests, setGuests] = useState([])
  const [name, setName] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    fetch('/api/admin/accounts')
      .then((response) => response.json())
      .then((body) => setGuests((body.accounts || []).filter((account) => account.role === 'guest')))
      .catch((err) => setError(err.message || 'Список аккаунтов недоступен'))
  }, [])

  async function register(event) {
    event.preventDefault()
    const clean = name.trim()
    if (!clean || busy) return
    setBusy(true)
    setError('')
    try {
      const response = await fetch('/api/admin/accounts', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: clean }),
      })
      const body = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(body.detail || `Шлюз ответил ${response.status}`)
      onEnter(body)
    } catch (err) {
      setError(err.message || 'Регистрация не прошла')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="w-full max-w-xl rounded-3xl bg-paper p-6 text-ink shadow-lg">
      <div className="flex items-start justify-between gap-4">
        <h1 className="font-serif text-4xl">Регистрация</h1>
        <button type="button" onClick={onClose} className="text-sm text-mute">
          Закрыть
        </button>
      </div>
      <p className="mt-3 text-mute">Пароль не нужен. Новый аккаунт или вход в уже существующий.</p>
      {error && <p className="mt-3 text-sm text-clay">{error}</p>}
      <form onSubmit={register} className="mt-6 flex flex-col gap-2">
        <label className="text-sm" htmlFor="guest-name">
          Имя
        </label>
        <input
          id="guest-name"
          value={name}
          onChange={(event) => setName(event.target.value)}
          placeholder="Как к вам обращаться"
          className="rounded-xl border border-line bg-panel px-3 py-2 outline-none focus:border-pine"
        />
        <button
          type="submit"
          disabled={busy || !name.trim()}
          className="rounded-xl bg-pine px-4 py-3 text-panel disabled:opacity-40"
        >
          Зарегистрироваться
        </button>
      </form>
      <h2 className="mt-6 font-serif text-xl">Войти</h2>
      {guests.length === 0 ? (
        <p className="mt-2 text-sm text-mute">Аккаунтов пока нет.</p>
      ) : (
        <ul className="mt-2 flex flex-col gap-2">
          {guests.map((account) => (
            <li key={account.id}>
              <button
                type="button"
                disabled={busy}
                onClick={() => onEnter(account)}
                className="w-full rounded-2xl border border-line bg-panel px-3 py-2 text-left hover:border-pine disabled:opacity-40"
              >
                Войти · {account.name}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

function WhoAreYou({ onChoose, onClose }) {
  return (
    <div className="w-full max-w-xl rounded-3xl bg-paper p-6 text-ink shadow-lg">
      <div className="flex items-start justify-between gap-4">
        <h1 className="font-serif text-4xl">Кто вы?</h1>
        <button type="button" onClick={onClose} className="text-sm text-mute">
          Закрыть
        </button>
      </div>
      <p className="mt-3 text-mute">Пароль не нужен. Клиент регистрируется или входит в свой аккаунт.</p>
      <div className="mt-6 grid gap-3">
          <button
            type="button"
            onClick={() => onChoose('guest')}
            className="rounded-2xl border border-line bg-panel px-5 py-4 text-left hover:border-pine"
          >
            <span className="block font-medium">Я клиент</span>
            <span className="mt-1 block text-sm text-mute">Новый аккаунт или вход, если уже регистрировались.</span>
          </button>
          <button
            type="button"
            onClick={() => onChoose('hotelier')}
            className="rounded-2xl border border-line bg-panel px-5 py-4 text-left hover:border-pine"
          >
            <span className="block font-medium">Я отельер</span>
            <span className="mt-1 block text-sm text-mute">Отвечаю, какие номера смотрят на эту стену.</span>
          </button>
        </div>
    </div>
  )
}

function App() {
  const [cabinet, setCabinet] = useState(null)
  const [askRole, setAskRole] = useState(false)
  const [guestGate, setGuestGate] = useState(false)
  const [messages, setMessages] = useState([{ role: 'agent', text: GREETING }])
  const [draft, setDraft] = useState('')
  const [busy, setBusy] = useState(false)
  const [hotels, setHotels] = useState([])
  const [cardSheet, setCardSheet] = useState(null)
  const [hotelNote, setHotelNote] = useState('Здесь будут две стены. Этого в карточке до брони нет.')
  const [guestId, setGuestId] = useState('')
  const [guestName, setGuestName] = useState('')
  const [picked, setPicked] = useState(null)
  const [chosen, setChosen] = useState(null)
  const [sheet, setSheet] = useState('closed')
  const [pane, setPane] = useState(416)
  const [stayDates, setStayDates] = useState('')
  const [intakeWaiting, setIntakeWaiting] = useState(false)
  const [intakeHint, setIntakeHint] = useState('')
  const [hotelierChatSeed, setHotelierChatSeed] = useState('')
  const [pendingHotelierChat, setPendingHotelierChat] = useState('')
  const [carouselShift, setCarouselShift] = useState('right')
  const [carouselDock, setCarouselDock] = useState('center')
  const [leftSheet, setLeftSheet] = useState('closed')
  const [leftPane, setLeftPane] = useState(416)
  const [carouselRegion, setCarouselRegion] = useState('Москва')

  function dragLeftPane(event) {
    event.preventDefault()
    event.stopPropagation()
    const handle = event.currentTarget
    if (handle.setPointerCapture) handle.setPointerCapture(event.pointerId)
    const startX = event.clientX
    const start = leftPane
    const move = (ev) => {
      const next = start + (ev.clientX - startX)
      const max = Math.max(280, Math.min(window.innerWidth - 280, window.innerWidth * 0.72))
      setLeftPane(Math.round(Math.min(Math.max(next, 280), max)))
    }
    const up = (ev) => {
      if (handle.releasePointerCapture && ev.pointerId === event.pointerId) {
        handle.releasePointerCapture(event.pointerId)
      }
      window.removeEventListener('pointermove', move)
      window.removeEventListener('pointerup', up)
      window.removeEventListener('pointercancel', up)
    }
    window.addEventListener('pointermove', move)
    window.addEventListener('pointerup', up)
    window.addEventListener('pointercancel', up)
  }

  function onLeftArrowClick() {
    if (leftSheet === 'side') {
      setLeftSheet('closed')
      return
    }
    setSheet('closed')
    setLeftSheet('side')
  }

  function onRightArrowClick() {
    if (leftSheet === 'side') {
      setLeftSheet('closed')
      return
    }
    if (sheet !== 'closed') {
      setSheet('closed')
      return
    }
    setLeftSheet('closed')
    setSheet('side')
  }

  const leftPanelOpen = leftSheet === 'side'
  const rightPanelOpen = sheet === 'side' || sheet === 'full'
  const leftArrowDirection = rightPanelOpen ? 'left' : leftPanelOpen ? 'left' : carouselShift
  const rightArrowDirection = leftPanelOpen ? 'right' : rightPanelOpen ? 'right' : carouselShift
  const leftArrowInset = leftPanelOpen ? leftPane : 0
  const rightArrowInset = sheet === 'side' ? pane : 0

  useEffect(() => {
    if (sheet === 'side' || sheet === 'full') {
      setLeftSheet('closed')
      setCarouselDock('right')
    } else if (leftSheet === 'side') {
      setCarouselDock('left')
    } else {
      setCarouselDock('center')
    }
  }, [sheet, leftSheet])

  function dragPane(event) {
    event.preventDefault()
    event.stopPropagation()
    const handle = event.currentTarget
    if (handle.setPointerCapture) handle.setPointerCapture(event.pointerId)
    const startX = event.clientX
    const start = pane
    const move = (ev) => {
      const next = start + (startX - ev.clientX)
      const max = Math.max(280, Math.min(window.innerWidth - 280, window.innerWidth * 0.72))
      setPane(Math.round(Math.min(Math.max(next, 280), max)))
    }
    const up = (ev) => {
      if (handle.releasePointerCapture && ev.pointerId === event.pointerId) {
        handle.releasePointerCapture(event.pointerId)
      }
      window.removeEventListener('pointermove', move)
      window.removeEventListener('pointerup', up)
      window.removeEventListener('pointercancel', up)
    }
    window.addEventListener('pointermove', move)
    window.addEventListener('pointerup', up)
    window.addEventListener('pointercancel', up)
  }

  function choose(next) {
    setAskRole(false)
    if (next === 'guest') {
      setGuestGate(true)
      return
    }
    setCabinet(next)
  }

  async function ask(history, guest) {
    setBusy(true)
    try {
      const userLines = history
        .filter((message) => message.role === 'user')
        .map((message) => message.text.trim())
        .filter(Boolean)
      const query = userLines.join('\n')
      const response = await fetch('/api/search', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query, dates: stayDates, hotel_id: picked || '', guest_id: guest }),
      })
      const body = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(body.detail || `Шлюз ответил ${response.status}`)
      const parsedDates = body.dates || body.slots?.dates || ''
      if (parsedDates) setStayDates(parsedDates)
      const dialogue = body.dialogue || {}
      const replyRole = dialogue.route === 'hotelier' ? 'hotelier' : 'agent'
      const agentReply = {
        role: replyRole,
        text: dialogue.reply || 'Ответ пустой.',
        hotelierChat: Boolean(dialogue.suggest_hotelier_chat),
        hotelierChatQuestion: dialogue.hotelier_chat_question || '',
      }
      const next = [...history, agentReply]
      if (dialogue.follow_up) {
        next.push({ role: 'agent', text: dialogue.follow_up, cta: true })
      }
      for (const question of dialogue.asks_user || []) {
        next.push({ role: 'agent', text: question, ask: true })
      }
      setMessages(next)
      if (dialogue.guest_id) setGuestId(dialogue.guest_id)
      const offered = (dialogue.hotels || []).slice(0, 3)
      if (dialogue.paid) {
        setIntakeWaiting(false)
        setIntakeHint('')
        const booked = (dialogue.hotels || []).slice(0, 1)
        if (booked.length) {
          setHotels(booked)
          setChosen(booked[0].id)
          setPicked(booked[0].id)
          setHotelNote(booked[0].name || 'Ваш отель.')
          setSheet('side')
        }
      } else if (dialogue.waiting) {
        const asks = (dialogue.asks_user || []).filter(Boolean)
        setIntakeWaiting(true)
        setIntakeHint(asks.join(' ') || 'Ответьте на вопрос агента в чате слева.')
        setCardSheet(null)
        setHotels([])
        setChosen(null)
        setPicked(null)
        setHotelNote(
          parsedDates
            ? 'Даты приняты. Ответьте на следующий вопрос — затем покажем отели.'
            : 'Сначала ответьте на вопросы агента — затем здесь появятся отели.',
        )
        setSheet((current) => (current === 'closed' ? 'side' : current))
      } else {
        setIntakeWaiting(false)
        setIntakeHint('')
        setCardSheet(dialogue.sheet || null)
        if (dialogue.sheet || offered.length) setSheet('side')
        if (offered.length) {
          setHotels(offered)
          const only = offered.length === 1 ? offered[0].id : null
          setChosen(only)
          setPicked(only)
          setHotelNote(only ? offered[0].name : 'Три отеля.')
        } else if ((dialogue.cards || []).length) {
          setHotels([])
          setChosen(null)
          if (body.slots?.hotel_id) setPicked(body.slots.hotel_id)
          setHotelNote(dialogue.sheet ? dialogue.sheet.address || '' : 'Открыта запрошенная карта.')
        } else {
          setHotels([])
          setChosen(null)
          setHotelNote('Подходящих отелей нет.')
        }
      }
    } catch (err) {
      setMessages([...history, { role: 'agent', text: err.message || 'Шлюз недоступен' }])
    } finally {
      setBusy(false)
    }
  }

  async function submit(text) {
    const clean = text.trim()
    if (!clean || busy) return
    const history = [...messages, { role: 'user', text: clean }]
    setMessages(history)
    setDraft('')
    await ask(history, guestId)
  }

  function enterGuest(account) {
    setGuestId(account.id)
    setGuestName(account.name || '')
    setGuestGate(false)
    setAskRole(false)
    if (pendingHotelierChat) {
      setHotelierChatSeed(pendingHotelierChat)
      setPendingHotelierChat('')
    }
    setCabinet('guest')
  }

  function openHotelierChat(questionText) {
    const clean = (questionText || '').trim()
    if (!clean) return
    if (!guestId) {
      setPendingHotelierChat(clean)
      setGuestGate(true)
      return
    }
    setHotelierChatSeed(clean)
    setCabinet('guest')
  }

  function openRegistration() {
    if (guestId) {
      setCabinet('guest')
      return
    }
    setAskRole(true)
  }

  function continueFromCabinet(payload) {
    if (!payload) return
    setCabinet(null)
    setGuestId((current) => current || payload.guest_id || '')
    if (payload.hotel_id) {
      setPicked(payload.hotel_id)
      setChosen(payload.hotel_id)
    }
    const booking = payload.booking
    if (booking?.check_in) {
      const end = booking.check_out && booking.check_out !== booking.check_in ? booking.check_out : ''
      setStayDates(end ? `${booking.check_in}/${end}` : booking.check_in)
    }
    const answerRole = payload.route === 'hotelier' ? 'hotelier' : 'agent'
    setMessages([
      { role: 'agent', text: payload.header || 'Ваш вопрос после брони.' },
      { role: 'user', text: payload.question || '' },
      {
        role: answerRole,
        text: payload.reply || '',
        hotelierChat: Boolean(payload.suggest_hotelier_chat),
        hotelierChatQuestion: payload.question || '',
      },
    ])
    setIntakeWaiting(false)
    setIntakeHint('')
  }

  function send(event) {
    event.preventDefault()
    submit(draft)
  }

  if (cabinet === 'guest') {
    return (
      <Admin
        entry="guest"
        onBack={() => setCabinet(null)}
        preferredHotelId={picked || ''}
        initialAccountId={guestId || ''}
        initialStayDates={stayDates}
        onContinueOnMain={continueFromCabinet}
        initialHotelierQuestion={hotelierChatSeed}
        onHotelierChatOpened={() => setHotelierChatSeed('')}
      />
    )
  }
  if (cabinet === 'hotelier') return <Admin entry="hotelier" onBack={() => setCabinet(null)} />

  const focus = chosen ? hotels.find((hotel) => hotel.id === chosen) : null
  const shown = focus ? [focus] : hotels
  const issuance = (
    <>
      <div className="flex items-start justify-between gap-3 pr-20">
        <div>
          <h2 className="font-serif text-2xl">
            {cardSheet?.title || focus?.name || (hotels.length ? 'Отели' : intakeWaiting ? 'Уточняем запрос' : 'Стороны')}
          </h2>
          <p className="mt-1 text-sm text-mute">{cardSheet ? cardSheet.address : focus?.address || hotelNote}</p>
        </div>
        <div className="flex shrink-0 gap-2">
          {sheet === 'full' ? (
            <button
              type="button"
              onClick={(event) => {
                event.stopPropagation()
                setSheet('side')
              }}
              className="rounded-xl border border-line px-3 py-2 text-sm"
            >
              Свернуть
            </button>
          ) : (
            <button
              type="button"
              onClick={(event) => {
                event.stopPropagation()
                setSheet('full')
              }}
              className="rounded-xl border border-line px-3 py-2 text-sm"
            >
              На весь экран
            </button>
          )}
          <button
            type="button"
            onClick={(event) => {
              event.stopPropagation()
              setSheet('closed')
              if (leftSheet !== 'side') setCarouselDock('center')
            }}
            className="rounded-xl border border-line px-3 py-2 text-sm"
          >
            Закрыть
          </button>
        </div>
      </div>
      {intakeWaiting && (
        <div className="mt-4 rounded-2xl border border-dashed border-moss/40 bg-moss/5 px-4 py-3 text-sm">
          <p className="font-medium text-pine">Ответьте в чате слева</p>
          <p className="mt-1">{intakeHint}</p>
          {stayDates && (
            <p className="mt-2 text-xs text-moss">
              Даты зафиксированы: {stayDates.includes('/') ? stayDates.replace('/', ' → ') : `${stayDates} (1 ночь)`}
            </p>
          )}
          <p className="mt-2 text-xs text-mute">Когда ответы будут приняты, эта панель сама обновится отелями и картами.</p>
        </div>
      )}
      {cardSheet && <CardSheet sheet={cardSheet} />}
      {focus && hotels.length > 1 && (
        <button
          type="button"
          onClick={(event) => {
            event.stopPropagation()
            setChosen(null)
            setPicked(null)
          }}
          className="mt-3 text-sm text-moss"
        >
          Все три
        </button>
      )}
      <ul className="mt-4 flex flex-col gap-3">
        {shown.map((hotel) => (
          <li key={hotel.id}>
            <HotelDossier
              hotel={hotel}
              picked={Boolean(focus)}
              onPick={(event) => {
                event.stopPropagation()
                setPicked(hotel.id)
                setChosen(hotel.id)
              }}
              onChoose={
                focus
                  ? null
                  : (event) => {
                      event.stopPropagation()
                      submit(`Я выбираю ${hotel.name || hotel.id}`)
                    }
              }
            />
          </li>
        ))}
      </ul>
    </>
  )

  return (
    <div className="min-h-svh bg-paper text-ink">
      <button
        type="button"
        onClick={openRegistration}
        className="fixed top-4 right-4 z-40 flex flex-col items-center gap-1 rounded-2xl border border-line bg-panel px-3 py-2 text-pine"
      >
        <svg viewBox="0 0 24 24" aria-hidden="true" className="h-6 w-6 fill-none stroke-current stroke-2">
          <circle cx="12" cy="8" r="3" />
          <path d="M5 19c1.5-3 3.8-4.5 7-4.5S17.5 16 19 19" />
        </svg>
        <span className="text-xs">{guestName || 'Регистрация'}</span>
      </button>
      <div
        style={{
          paddingRight: sheet === 'side' ? pane : undefined,
          paddingLeft: leftSheet === 'side' ? leftPane : undefined,
        }}
      >
        <section className="mx-auto flex min-h-svh w-full max-w-3xl flex-col px-5">
          <div className="relative w-full overflow-visible pt-4 sm:pt-6">
            <HotelCarousel dock={carouselDock} onShiftDirection={setCarouselShift} />
          </div>
          <header className="mx-auto w-full max-w-[36rem] pt-6 text-center sm:pt-8">
            <h1 className="w-full font-serif text-4xl leading-tight text-pine sm:text-5xl">Создай свой островок</h1>
            {guestName ? (
              <p className="mt-2 text-sm text-mute">
                Здравствуйте, <span className="font-medium text-ink">{guestName}</span>
              </p>
            ) : (
              <p className="mt-2 text-sm text-mute">Подберём отель под ваш запрос</p>
            )}
          </header>
          <div className="mx-auto flex w-full max-w-[36rem] flex-1 flex-col gap-3 overflow-x-hidden overflow-y-auto pb-4">
            {messages.map((message, index) => (
              <p
                key={`${message.role}-${index}`}
                className={
                  message.role === 'user'
                    ? 'max-w-[36rem] self-end rounded-2xl bg-pine px-4 py-3 whitespace-pre-line text-panel'
                    : message.role === 'hotelier' || message.role === 'faq_agent'
                      ? 'max-w-[36rem] self-start rounded-2xl border border-line bg-panel px-4 py-3 whitespace-pre-line shadow-sm'
                      : 'max-w-[36rem] self-start rounded-2xl bg-panel px-4 py-3 whitespace-pre-line shadow-sm'
                }
              >
                <span className="mb-1 block text-xs tracking-wide uppercase opacity-70">
                  {message.role === 'user'
                    ? 'Вы'
                    : message.role === 'hotelier'
                      ? 'Отельер'
                      : message.role === 'faq_agent'
                        ? 'Отельер'
                        : 'Агент'}
                  {message.ask ? ' · вопрос' : ''}
                </span>
                {message.text}
                {message.hotelierChat && (
                  <button
                    type="button"
                    onClick={() => openHotelierChat(message.hotelierChatQuestion || message.text)}
                    className="mt-3 inline-flex items-center gap-2 rounded-xl border border-pine bg-paper px-3 py-2 text-sm text-pine hover:bg-moss/10"
                  >
                    <svg viewBox="0 0 24 24" aria-hidden="true" className="h-5 w-5 fill-none stroke-current stroke-2">
                      <path d="M4 5h16v10H5.2L4 16.2V5z" />
                      <path d="M8 9h8M8 12h5" />
                    </svg>
                    Чат с отельером
                  </button>
                )}
              </p>
            ))}
          </div>
          <form onSubmit={send} className="flex flex-col gap-2 border-t border-line py-4">
            <p className="text-center text-sm text-mute">{QUERY_SAMPLE}</p>
            <div className="flex gap-2">
            <label className="sr-only" htmlFor="query">
              Запрос
            </label>
            <textarea
              id="query"
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              rows={2}
              placeholder="Ваш запрос"
              className="min-h-14 flex-1 resize-none rounded-2xl border border-line bg-panel px-4 py-3 outline-none focus:border-pine"
            />
            <button
              type="submit"
              disabled={busy || !draft.trim()}
              className="self-end rounded-2xl bg-pine px-4 py-3 text-panel disabled:opacity-40"
            >
              {busy ? '…' : 'Отправить'}
            </button>
            </div>
          </form>
          {(askRole || guestGate) && (
            <div className="fixed inset-0 z-50 flex items-center justify-center bg-ink/40 px-5">
              {guestGate ? (
                <GuestGate onEnter={enterGuest} onClose={() => setGuestGate(false)} />
              ) : (
                <WhoAreYou onChoose={choose} onClose={() => setAskRole(false)} />
              )}
            </div>
          )}
        </section>
      </div>
      <CarouselShiftIndicator
        direction={leftArrowDirection}
        edge="left"
        inset={leftArrowInset}
        onClick={onLeftArrowClick}
        titleExtra={leftPanelOpen ? 'Закрыть выбор региона' : 'Открыть выбор региона'}
      />
      <CarouselShiftIndicator
        direction={rightArrowDirection}
        edge="right"
        inset={rightArrowInset}
        onClick={onRightArrowClick}
        titleExtra={
          leftPanelOpen
            ? 'Вернуть карусель'
            : sheet !== 'closed'
              ? 'Закрыть выдачу'
              : `Открыть выдачу${
                  intakeWaiting ? ' · ждём ответ' : hotels.length ? ` · ${hotels.length} отелей` : cardSheet ? ' · карта' : ''
                }`
        }
      />
      <aside
        style={leftSheet === 'side' ? { width: leftPane } : undefined}
        className={`fixed top-0 left-0 z-30 flex h-svh border-r border-line bg-paper shadow-xl transition-transform duration-300 ${
          leftSheet === 'closed' ? 'pointer-events-none -translate-x-full' : 'translate-x-0 flex-row'
        }`}
      >
        <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">
          <h2 className="font-serif text-xl text-pine">Регион</h2>
          <p className="mt-1 text-sm text-mute">Выберите регион для подбора отелей</p>
          <ul className="mt-4 space-y-1">
            {CAROUSEL_REGIONS.map((name) => (
              <li key={name}>
                <button
                  type="button"
                  onClick={() => setCarouselRegion(name)}
                  className={`w-full rounded-xl px-3 py-2 text-left text-sm ${
                    carouselRegion === name
                      ? 'bg-pine text-panel'
                      : 'text-ink hover:bg-moss/10'
                  }`}
                >
                  {name}
                </button>
              </li>
            ))}
          </ul>
          <p className="mt-4 text-sm text-mute">
            Сейчас: <span className="font-medium text-ink">{carouselRegion}</span>
          </p>
        </div>
        {leftSheet === 'side' && (
          <div
            role="separator"
            aria-orientation="vertical"
            aria-label="Ширина панели региона"
            title="Потяните, чтобы изменить ширину"
            onPointerDown={dragLeftPane}
            className="relative z-20 w-3 shrink-0 cursor-col-resize touch-none select-none border-l border-moss/25 bg-moss/5 hover:bg-moss/15 active:bg-moss/25"
          />
        )}
      </aside>
      <aside
        style={sheet === 'full' ? undefined : sheet === 'side' ? { width: pane } : undefined}
        className={`fixed top-0 right-0 z-30 flex h-svh border-l border-line bg-paper shadow-xl transition-transform duration-300 ${
          sheet === 'closed'
            ? 'translate-x-full'
            : sheet === 'full'
              ? 'w-full translate-x-0 flex-col overflow-y-auto px-5 py-4'
              : 'translate-x-0 flex-row'
        }`}
      >
        {sheet === 'side' && (
          <div
            role="separator"
            aria-orientation="vertical"
            aria-label="Ширина выдачи"
            title="Потяните, чтобы изменить ширину"
            onPointerDown={dragPane}
            className="relative z-20 w-3 shrink-0 cursor-col-resize touch-none select-none border-r border-moss/25 bg-moss/5 hover:bg-moss/15 active:bg-moss/25"
          />
        )}
        <div
          className={`min-h-0 flex-1 overflow-y-auto px-5 py-4 ${sheet === 'side' ? 'cursor-pointer' : ''}`}
          onClick={() => {
            if (sheet === 'side') setSheet('full')
          }}
        >
          {issuance}
        </div>
      </aside>
    </div>
  )
}

export default App
