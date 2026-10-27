import { useEffect, useRef, useState } from 'react'

function iso(offset) {
  const day = new Date()
  day.setDate(day.getDate() + offset)
  const month = String(day.getMonth() + 1).padStart(2, '0')
  const date = String(day.getDate()).padStart(2, '0')
  return `${day.getFullYear()}-${month}-${date}`
}

/** Как backend `_stay_bounds`: одна дата → выезд на следующий день. */
export function boundsFromStayDates(dates) {
  const trimmed = (dates || '').trim()
  if (!trimmed) return null
  const slash = trimmed.indexOf('/')
  const checkIn = slash >= 0 ? trimmed.slice(0, slash) : trimmed
  let checkOut = slash >= 0 ? trimmed.slice(slash + 1) : ''
  if (!checkOut || checkOut === checkIn) {
    const end = new Date(`${checkIn}T00:00:00`)
    if (Number.isNaN(end.getTime())) return null
    end.setDate(end.getDate() + 1)
    checkOut = `${end.getFullYear()}-${String(end.getMonth() + 1).padStart(2, '0')}-${String(end.getDate()).padStart(2, '0')}`
  }
  if (Number.isNaN(new Date(`${checkIn}T00:00:00`).getTime())) return null
  if (Number.isNaN(new Date(`${checkOut}T00:00:00`).getTime())) return null
  return { checkIn, checkOut }
}

function nightsBetween(checkIn, checkOut) {
  const start = new Date(`${checkIn}T00:00:00`)
  const end = new Date(`${checkOut}T00:00:00`)
  return Math.round((end - start) / 86400000)
}

function nightWord(count) {
  const tail = count % 100
  const last = count % 10
  const word = tail >= 11 && tail <= 14 ? 'ночей' : last === 1 ? 'ночь' : last >= 2 && last <= 4 ? 'ночи' : 'ночей'
  return `${count} ${word}`
}

function rub(amount) {
  return `${Number(amount).toLocaleString('ru-RU')} ₽`
}

const HOTELIER_CHAT_EXAMPLES = [
  'Можно с животными?',
  'Какая сторона тише ночью?',
  'Тише улица или двор?',
  'Во сколько завтрак?',
  'Есть ли парковка?',
]

function isGuestChatMessage(message, accountId) {
  if (!accountId) return false
  const mine = message.guest_id === accountId || message.author_id === accountId
  if (!mine) return false
  if (message.author_role === 'guest') return true
  if (message.author_role !== 'hotelier') return false
  const body = message.body || ''
  return !/primary «|tertiary «|Счёт отеля|facade_noise|стриптиз/i.test(body)
}

function chatCaption(message) {
  if (message.author_role === 'guest') return 'Вопрос'
  if (message.author_id === 'fact-snapshot') return 'Ответ · снимок окрестностей'
  if (message.author_id === 'hotel-kb') return 'Ответ · база знаний'
  if (message.author_id === 'gigachat') return 'Ответ · GigaChat'
  if (message.author_id === 'hotelier-live') return 'Ответ · живой отельер'
  return 'Ответ'
}

const FAQ_SECTIONS = [
  { id: 'checkin', title: 'Заезд / выезд', placeholder: 'Заезд с 15:00, выезд до 12:00…' },
  { id: 'breakfast', title: 'Завтрак', placeholder: 'Время, формат, входит ли в цену…' },
  { id: 'parking', title: 'Парковка', placeholder: 'Есть ли места, цена, дистанция до входа…' },
  { id: 'pets', title: 'С питомцами', placeholder: 'Кого пускаете, доплата, правила…' },
  { id: 'other', title: 'Прочее', placeholder: 'Wi‑Fi, багаж, трансфер…' },
]

const FAQ_DEFAULT = {
  checkin: 'Заезд с 15:00, выезд до 12:00. Ранний заезд и поздний выезд — по запросу, если есть свободные номера.',
  breakfast: 'Завтрак «шведский стол» 07:00–11:00. В тариф не входит, оплата на месте.',
  parking: 'Охраняемой парковки у здания нет. Ближайшие платные места — уточняйте на ресепшене.',
  pets: '',
  other: 'Wi‑Fi в лобби и номерах. Багаж можно оставить до заезда, если есть место на складе.',
}

function applyFaqState(body, setters) {
  if (!body) return
  setters.setFaqEnabled(Boolean(body.enabled))
  setters.setFaqSections({ ...FAQ_DEFAULT, ...(body.sections || {}) })
  setters.setFaqDocuments(body.documents || [])
  setters.setFaqChunkCount(body.chunk_count || 0)
  setters.setFaqSavedAt(body.updated_at || null)
}

async function read(url, options) {
  const response = await fetch(url, options)
  const body = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(body.detail || `Шлюз ответил ${response.status}`)
  return body
}

function Admin({
  entry = '',
  onBack,
  preferredHotelId = '',
  initialAccountId = '',
  initialStayDates = '',
  onContinueOnMain = null,
  initialHotelierQuestion = '',
  onHotelierChatOpened = null,
}) {
  const [catalog, setCatalog] = useState({ accounts: [], hotels: [], registrations: [], night_rub: 10000, payment_note: '' })
  const [accountId, setAccountId] = useState(() => initialAccountId || (entry === 'guest' ? 'guest' : ''))
  const [hotelName, setHotelName] = useState('Пекин')
  const [hotelAddress, setHotelAddress] = useState('Большая Садовая улица, 5/1')
  const [registeredNote, setRegisteredNote] = useState('')
  const [desk, setDesk] = useState(null)
  const [hotelId, setHotelId] = useState('')
  const initialBounds = boundsFromStayDates(initialStayDates)
  const [checkIn, setCheckIn] = useState(() => initialBounds?.checkIn || iso(1))
  const [checkOut, setCheckOut] = useState(() => initialBounds?.checkOut || iso(2))
  const [question, setQuestion] = useState('')
  const [reply, setReply] = useState('')
  const [receipt, setReceipt] = useState(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [faqEnabled, setFaqEnabled] = useState(false)
  const [faqSections, setFaqSections] = useState(() => ({ ...FAQ_DEFAULT }))
  const [faqSavedAt, setFaqSavedAt] = useState(null)
  const [faqNotice, setFaqNotice] = useState('')
  const [faqDocuments, setFaqDocuments] = useState([])
  const [faqChunkCount, setFaqChunkCount] = useState(0)
  const [faqTestQuestion, setFaqTestQuestion] = useState('')
  const [faqTestResult, setFaqTestResult] = useState(null)
  const hotelierSeedRef = useRef('')
  const chatSectionRef = useRef(null)

  useEffect(() => {
    read('/api/admin/accounts')
      .then((body) => {
        setCatalog(body)
        setHotelId((current) => preferredHotelId || current || body.hotels?.[0]?.id || '')
      })
      .catch((err) => setError(err.message))
  }, [preferredHotelId])

  useEffect(() => {
    if (preferredHotelId) setHotelId(preferredHotelId)
  }, [preferredHotelId])

  useEffect(() => {
    if (initialAccountId) setAccountId(initialAccountId)
  }, [initialAccountId])

  useEffect(() => {
    const bounds = boundsFromStayDates(initialStayDates)
    if (bounds) {
      setCheckIn(bounds.checkIn)
      setCheckOut(bounds.checkOut)
    }
  }, [initialStayDates])

  useEffect(() => {
    if (!accountId) {
      setDesk(null)
      return
    }
    const url = new URL(window.location.href)
    url.searchParams.set('account', accountId)
    window.history.replaceState(null, '', url)
    read(`/api/admin/accounts/${accountId}`)
      .then((body) => {
        setDesk(body)
        if (body.account?.role !== 'hotelier') setReply(body.draft || '')
        applyFaqState(body.faq, {
          setFaqEnabled,
          setFaqSections,
          setFaqDocuments,
          setFaqChunkCount,
          setFaqSavedAt,
        })
        setError('')
      })
      .catch((err) => {
        setError(err.message)
        if (entry === 'guest' && onBack && /счёта нет/i.test(err.message || '')) onBack()
      })
  }, [accountId])

  const account = desk?.account
  const nights = nightsBetween(checkIn, checkOut)
  const amount = nights > 0 ? nights * (desk?.night_rub || catalog.night_rub) : 0
  const thread = account?.role === 'hotelier'
    ? desk?.threads?.[account.hotel_id] || []
    : desk?.threads?.[hotelId] || []
  const paidBooking = (desk?.bookings || []).find(
    (item) => item.status === 'paid' && item.hotel_id === hotelId,
  )

  useEffect(() => {
    if (!initialHotelierQuestion?.trim() || !paidBooking || !account?.id || !desk) return
    if (hotelierSeedRef.current === initialHotelierQuestion) return
    hotelierSeedRef.current = initialHotelierQuestion
    setQuestion(initialHotelierQuestion)
    askHotelier(initialHotelierQuestion).finally(() => onHotelierChatOpened?.())
  }, [initialHotelierQuestion, paidBooking, account?.id, desk])
  const guestChatThread = thread.filter((message) => isGuestChatMessage(message, account?.id))

  async function registerHotel(event) {
    event.preventDefault()
    if (!hotelName.trim()) return
    setBusy(true)
    setError('')
    try {
      const created = await read('/api/admin/register-hotel', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: hotelName.trim(), address: hotelAddress.trim() }),
      })
      setCatalog(await read('/api/admin/accounts'))
      setAccountId(created.account_id)
      setRegisteredNote(
        created.in_snapshot
          ? 'Отель есть в снимке. Кабинет связан с его фактами.'
          : 'В снимке OSM такого названия нет. Кабинет создан, факты фасада не подставлены.',
      )
      setHotelName('')
      setHotelAddress('')
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  async function pay(event) {
    event.preventDefault()
    if (!account || account.role !== 'guest') return
    setBusy(true)
    setReceipt(null)
    try {
      const body = await read('/api/admin/pay', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          guest_id: account.id,
          hotel_id: hotelId,
          check_in: checkIn,
          check_out: checkOut,
        }),
      })
      setReceipt(body.booking)
      setDesk(await read(`/api/admin/accounts/${account.id}`))
      setQuestion('')
      requestAnimationFrame(() => chatSectionRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }))
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  function submitHotelierChat(event) {
    event.preventDefault()
    askHotelier()
  }

  async function hideMessage(messageId, scope) {
    if (!account?.id || busy) return
    setBusy(true)
    setError('')
    try {
      setDesk(
        await read('/api/admin/messages/hide', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ account_id: account.id, message_id: messageId, scope }),
        }),
      )
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  async function askHotelier(text) {
    const clean = (text || question).trim()
    if (!clean || !account) return
    setBusy(true)
    setError('')
    try {
      const body = await read('/api/admin/ask', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ guest_id: account.id, hotel_id: hotelId, text: clean }),
      })
      setDesk((current) => ({ ...current, threads: { ...current.threads, ...body.threads } }))
      setQuestion('')
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  async function saveFaqTemplate(event) {
    event.preventDefault()
    if (!account?.hotel_id) return
    setBusy(true)
    setFaqNotice('')
    try {
      const body = await read(`/api/faq/hotels/${account.hotel_id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled: faqEnabled, sections: faqSections }),
      })
      applyFaqState(body, {
        setFaqEnabled,
        setFaqSections,
        setFaqDocuments,
        setFaqChunkCount,
        setFaqSavedAt,
      })
      setFaqNotice(`Сохранено. В индексе RAG: ${body.chunk_count} фрагментов.`)
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  async function uploadKbFile(event) {
    const file = event.target.files?.[0]
    event.target.value = ''
    if (!file || !account?.hotel_id) return
    setBusy(true)
    setFaqNotice('')
    try {
      const form = new FormData()
      form.append('file', file)
      const response = await fetch(`/api/faq/hotels/${account.hotel_id}/upload`, { method: 'POST', body: form })
      const body = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(body.detail || `Шлюз ответил ${response.status}`)
      applyFaqState(body, {
        setFaqEnabled,
        setFaqSections,
        setFaqDocuments,
        setFaqChunkCount,
        setFaqSavedAt,
      })
      setFaqNotice(`Файл «${file.name}» проиндексирован.`)
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  async function removeKbDocument(documentId, filename) {
    if (!account?.hotel_id || !documentId) return
    setBusy(true)
    setFaqNotice('')
    setError('')
    try {
      const body = await read(`/api/faq/hotels/${account.hotel_id}/documents/${documentId}`, {
        method: 'DELETE',
      })
      applyFaqState(body, {
        setFaqEnabled,
        setFaqSections,
        setFaqDocuments,
        setFaqChunkCount,
        setFaqSavedAt,
      })
      setFaqNotice(`«${filename}» удалён из базы знаний.`)
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  async function testFaqAgent(event) {
    event?.preventDefault?.()
    if (!account?.hotel_id || !faqTestQuestion.trim()) return
    setBusy(true)
    setFaqTestResult(null)
    try {
      const body = await read(`/api/faq/hotels/${account.hotel_id}/ask`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: faqTestQuestion.trim() }),
      })
      setFaqTestResult(body)
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  async function sendReply(event) {
    event.preventDefault()
    if (!reply.trim() || !account) return
    setBusy(true)
    try {
      const body = await read('/api/admin/reply', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ account_id: account.id, text: reply.trim() }),
      })
      setDesk((current) => ({ ...current, threads: { ...current.threads, ...body.threads } }))
      setReply('')
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  const guestDesk = account?.role === 'guest' && (
    <>
      <header>
        <h2 className="font-serif text-2xl">Кабинет клиента</h2>
        <p className="mt-1 text-sm">
          {account?.name ? (
            <>
              Вы вошли как <span className="font-medium">{account.name}</span>
            </>
          ) : (
            'Ваш аккаунт'
          )}
        </p>
        <p className="mt-1 text-sm text-mute">{desk.payment_note}</p>
        {initialStayDates && boundsFromStayDates(initialStayDates) && (
          <p className="mt-2 text-xs text-moss">Даты заезда подставлены из диалога на главной.</p>
        )}
      </header>
      <label className="flex flex-col gap-1 text-sm">
        Отель
        <select
          value={hotelId}
          onChange={(event) => setHotelId(event.target.value)}
          className="rounded-xl border border-line bg-panel px-3 py-2"
        >
          {catalog.hotels.map((hotel) => (
            <option key={hotel.id} value={hotel.id}>
              {hotel.name}
            </option>
          ))}
        </select>
      </label>
      {!paidBooking ? (
        <form onSubmit={pay} className="grid gap-3 rounded-2xl border border-line bg-panel p-4">
          <div className="rounded-2xl border border-pine px-4 py-3 text-sm">
            <p className="font-medium">К оплате</p>
            <p className="mt-1">
              {nights > 0
                ? `${nightWord(nights)} · ${rub(amount)}. Номер карты не нужен, деньги не списываются.`
                : 'Выезд должен быть позже заезда.'}
            </p>
          </div>
          <label className="flex flex-col gap-1 text-sm">
            Заезд
            <input type="date" value={checkIn} onChange={(event) => setCheckIn(event.target.value)} className="rounded-xl border border-line px-3 py-2" />
          </label>
          <label className="flex flex-col gap-1 text-sm">
            Выезд
            <input type="date" value={checkOut} onChange={(event) => setCheckOut(event.target.value)} className="rounded-xl border border-line px-3 py-2" />
          </label>
          <button
            type="submit"
            disabled={busy || nights < 1}
            className="rounded-xl bg-pine px-4 py-3 text-panel disabled:opacity-40"
          >
            Забронировать
          </button>
        </form>
      ) : (
        <div className="rounded-2xl border border-pine bg-panel px-4 py-3 text-sm">
          <p className="font-medium">Бронь №{paidBooking.id} · {paidBooking.hotel_name}</p>
          <p className="mt-1 text-mute">
            {paidBooking.check_in} — {paidBooking.check_out}, {rub(paidBooking.amount_rub)}, оплачено
          </p>
        </div>
      )}
      {receipt && !paidBooking && (
        <p className="rounded-2xl border border-pine bg-panel px-4 py-3">
          Оплачено. Бронь №{receipt.id}, {receipt.hotel_name}, {receipt.check_in} — {receipt.check_out}, {rub(receipt.amount_rub)}.
        </p>
      )}
      {!paidBooking && (desk?.bookings || []).length > 0 && <BookingList bookings={desk.bookings} />}
      {paidBooking && (
        <section ref={chatSectionRef} className="rounded-2xl border border-line bg-panel p-4">
          <h3 className="font-serif text-xl">Чат с отельером</h3>
          <p className="mt-1 text-sm text-mute">
            Вопрос про парк, стадион и дорогу отвечает снимок окрестностей. Вопрос об отеле — база знаний. Если ответа нет, вопрос уходит живому отельеру.
          </p>
          {guestChatThread.length > 0 && (
            <div className="mt-4">
              <Thread messages={guestChatThread} onHide={hideMessage} />
            </div>
          )}
          <p className="mt-4 text-xs font-medium tracking-wide text-mute uppercase">Примеры вопросов</p>
          <ul className="mt-2 flex flex-col gap-2">
            {HOTELIER_CHAT_EXAMPLES.map((sample) => (
              <li key={sample}>
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => {
                    setQuestion(sample)
                    askHotelier(sample)
                  }}
                  className="w-full rounded-xl border border-line bg-paper px-3 py-2 text-left text-sm hover:border-pine"
                >
                  {sample}
                </button>
              </li>
            ))}
          </ul>
          <form onSubmit={submitHotelierChat} className="mt-4 flex flex-col gap-2">
            <textarea
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              rows={3}
              placeholder={HOTELIER_CHAT_EXAMPLES[0]}
              className="resize-none rounded-xl border border-line px-3 py-2 outline-none focus:border-pine"
            />
            <button
              type="submit"
              disabled={busy || !question.trim()}
              className="rounded-xl bg-pine px-4 py-3 text-panel disabled:opacity-40"
            >
              Отправить отельеру
            </button>
          </form>
        </section>
      )}
      {!paidBooking && (
        <p className="text-sm text-mute">После оплаты здесь откроется чат с отельером.</p>
      )}
    </>
  )

  if (entry === 'guest') {
    return (
      <div className="min-h-svh bg-paper text-ink">
        <div className="mx-auto flex max-w-xl flex-col gap-4 px-5 py-4">
          {onBack && (
            <button type="button" onClick={onBack} className="self-start text-sm text-moss underline">
              На главную
            </button>
          )}
          {error && <p className="rounded-2xl border border-clay px-4 py-3 text-clay">{error}</p>}
          {guestDesk || <p className="text-sm text-mute">Открываю кабинет клиента…</p>}
        </div>
      </div>
    )
  }

  const hotelierThread = (desk?.threads?.[account?.hotel_id] || []).filter(
    (message) => message.author_role !== 'system',
  )

  if (!account) {
    return (
      <div className="min-h-svh bg-paper text-ink">
        <div className="mx-auto flex max-w-xl flex-col gap-4 px-5 py-4">
          {onBack && (
            <button type="button" onClick={onBack} className="self-start text-sm text-moss underline">
              На главную
            </button>
          )}
          {accountId && !error ? (
            <p className="text-sm text-mute">Открываю кабинет отельера…</p>
          ) : (
            <>
              {error && <p className="rounded-2xl border border-clay px-4 py-3 text-clay">{error}</p>}
              <h1 className="font-serif text-4xl">Регистрация отеля</h1>
              <p className="text-mute">Сначала отель. После входа откроются чат и база знаний.</p>
              <form onSubmit={registerHotel} className="flex flex-col gap-2">
                <input
                  value={hotelName}
                  onChange={(event) => setHotelName(event.target.value)}
                  placeholder="Название отеля"
                  className="rounded-xl border border-line bg-panel px-3 py-2 outline-none focus:border-pine"
                />
                <input
                  value={hotelAddress}
                  onChange={(event) => setHotelAddress(event.target.value)}
                  placeholder="Адрес"
                  className="rounded-xl border border-line bg-panel px-3 py-2 outline-none focus:border-pine"
                />
                <button type="submit" disabled={busy || !hotelName.trim()} className="rounded-xl bg-pine px-4 py-3 text-panel disabled:opacity-40">
                  Зарегистрировать и войти
                </button>
              </form>
              <h2 className="font-serif text-xl">Войти</h2>
              {(catalog.registrations || []).length === 0 ? (
                <p className="text-sm text-mute">Зарегистрированных отелей пока нет.</p>
              ) : (
                <ul className="flex flex-col gap-2">
                  {(catalog.registrations || []).map((item) => (
                    <li key={item.account_id}>
                      <button
                        type="button"
                        onClick={() => setAccountId(item.account_id)}
                        className="w-full rounded-2xl border border-line bg-panel px-3 py-2 text-left hover:border-pine"
                      >
                        Войти · {item.name}
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </>
          )}
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-svh bg-paper text-ink">
      <div className="mx-auto flex max-w-xl flex-col gap-4 px-5 py-4">
        {onBack && (
          <button type="button" onClick={onBack} className="self-start text-sm text-moss underline">
            На главную
          </button>
        )}
        {error && <p className="rounded-2xl border border-clay px-4 py-3 text-clay">{error}</p>}
        <header>
          <p className="text-xs tracking-[0.18em] text-moss uppercase">Отельер</p>
          <h1 className="font-serif text-4xl">{account.name}</h1>
          {registeredNote && <p className="mt-1 text-sm">{registeredNote}</p>}
        </header>

        <section className="rounded-2xl border border-line bg-panel p-4">
          <h2 className="font-serif text-xl">Чат</h2>
          <p className="mt-1 text-sm text-mute">Вопросы гостя и ваши ответы. Лишнее можно скрыть только у себя или ещё и у гостя.</p>
          <div className="mt-4">
            <Thread messages={hotelierThread} onHide={hideMessage} hideBoth="Удалить у меня и у гостя" />
          </div>
          <form onSubmit={sendReply} className="mt-4 flex flex-col gap-2">
            <textarea
              value={reply}
              onChange={(event) => setReply(event.target.value)}
              rows={3}
              placeholder="Ответ гостю"
              className="resize-none rounded-xl border border-line px-3 py-2 outline-none focus:border-pine"
            />
            <button type="submit" disabled={busy || !reply.trim()} className="rounded-xl bg-pine px-4 py-3 text-panel disabled:opacity-40">
              Отправить
            </button>
          </form>
        </section>

        <form onSubmit={saveFaqTemplate} className="flex flex-col gap-4">
          <section className="rounded-2xl border border-line bg-panel p-4">
            <h2 className="font-serif text-xl">База знаний</h2>
            <p className="mt-1 text-sm text-mute">
              Загрузите файл или допишите темы. После сохранения гость получает ответ из этой базы.
            </p>
            <p className="mt-1 text-xs text-mute">В индексе {faqChunkCount} фрагментов.</p>
            <label className="mt-3 flex cursor-pointer items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={faqEnabled}
                onChange={(event) => setFaqEnabled(event.target.checked)}
                className="h-4 w-4 accent-pine"
              />
              {faqEnabled ? 'Ответы из базы включены' : 'Ответы из базы выключены'}
            </label>
            <label
              className={`mt-3 inline-flex cursor-pointer items-center justify-center rounded-xl bg-pine px-4 py-2.5 text-sm text-panel ${busy ? 'pointer-events-none opacity-40' : ''}`}
            >
              <input
                type="file"
                accept=".txt,.md,.json,text/plain,text/markdown,application/json"
                disabled={busy}
                onChange={uploadKbFile}
                className="sr-only"
              />
              Загрузить файл
            </label>
            <p className="mt-2 text-xs text-mute">UTF-8: .txt, .md, .json</p>
            {faqDocuments.length > 0 && (
              <ul className="mt-3 flex flex-col gap-1 text-xs text-mute">
                {faqDocuments.map((doc) => (
                  <li key={doc.id} className="flex items-start justify-between gap-2 rounded-lg bg-paper px-2 py-1">
                    <span className="min-w-0 flex-1">
                      {doc.filename} · {doc.chars} симв.
                    </span>
                    <button
                      type="button"
                      disabled={busy}
                      onClick={() => removeKbDocument(doc.id, doc.filename)}
                      className="shrink-0 text-clay disabled:opacity-40"
                    >
                      Удалить файл
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </section>

          {FAQ_SECTIONS.map((section) => (
            <label key={section.id} className="flex flex-col gap-1 rounded-2xl border border-line bg-panel p-4 text-sm">
              <span className="font-medium">{section.title}</span>
              <textarea
                value={faqSections[section.id] || ''}
                onChange={(event) =>
                  setFaqSections((current) => ({ ...current, [section.id]: event.target.value }))
                }
                rows={section.id === 'other' ? 3 : 2}
                placeholder={section.placeholder}
                className="resize-none rounded-xl border border-line px-3 py-2 outline-none focus:border-pine"
              />
            </label>
          ))}

          <section className="rounded-2xl border border-line bg-panel p-4">
            <p className="font-medium text-sm">Проверить вопрос</p>
            <div className="mt-2 flex flex-col gap-2">
              <input
                value={faqTestQuestion}
                onChange={(event) => setFaqTestQuestion(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter') {
                    event.preventDefault()
                    testFaqAgent(event)
                  }
                }}
                placeholder="Можно с животными?"
                className="rounded-xl border border-line px-3 py-2 text-sm outline-none focus:border-pine"
              />
              <button
                type="button"
                disabled={busy || !faqTestQuestion.trim()}
                onClick={testFaqAgent}
                className="rounded-xl border border-pine px-3 py-2 text-sm text-pine disabled:opacity-40"
              >
                Спросить базу
              </button>
            </div>
            {faqTestResult && <p className="mt-3 whitespace-pre-line text-sm">{faqTestResult.message}</p>}
          </section>

          <div className="flex flex-wrap items-center gap-3">
            <button type="submit" className="rounded-xl bg-pine px-4 py-3 text-panel">
              Сохранить базу
            </button>
            {faqNotice && <span className="text-sm text-moss">{faqNotice}</span>}
          </div>
        </form>
      </div>
    </div>
  )
}
function Thread({ messages, onHide, hideBoth = 'Удалить у меня и у отельера' }) {
  const [menuId, setMenuId] = useState(null)
  if (!messages.length) return <p className="text-sm text-mute">В переписке этого отеля пока пусто.</p>
  return (
    <ul className="flex flex-col gap-2">
      {messages.map((message) => {
        const question = message.author_role === 'guest'
        return (
          <li
            key={message.id}
            className={
              question
                ? 'rounded-2xl border border-line bg-paper px-4 py-3'
                : 'rounded-2xl border border-pine bg-panel px-4 py-3'
            }
          >
            <p className="text-xs font-medium tracking-wide text-moss uppercase">{chatCaption(message)}</p>
            <p className="mt-1 text-sm">{message.body}</p>
            {onHide &&
              (menuId === message.id ? (
                <div className="mt-2 flex flex-col items-start gap-1">
                  <button type="button" className="text-xs text-moss underline" onClick={() => onHide(message.id, 'me')}>
                    Удалить у меня
                  </button>
                  <button type="button" className="text-xs text-moss underline" onClick={() => onHide(message.id, 'both')}>
                    {hideBoth}
                  </button>
                </div>
              ) : (
                <button type="button" className="mt-2 text-xs text-mute underline" onClick={() => setMenuId(message.id)}>
                  Удалить
                </button>
              ))}
          </li>
        )
      })}
    </ul>
  )
}

function BookingList({ bookings }) {
  if (!bookings.length) return null
  return (
    <ul className="flex flex-col gap-2">
      {bookings.map((booking) => (
        <li key={booking.id} className="rounded-2xl border border-line px-4 py-3 text-sm">
          Бронь №{booking.id}: {booking.hotel_name}, {booking.check_in} — {booking.check_out}, {rub(booking.amount_rub)}, {booking.status === 'paid' ? 'оплачено' : booking.status}
        </li>
      ))}
    </ul>
  )
}

export default Admin
