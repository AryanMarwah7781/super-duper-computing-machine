import { useCallback, useEffect, useState } from "react"
import {
  closeLesson,
  completeStep,
  lessons as fetchLessons,
  onEvent,
  openLesson,
  resetLesson,
  whenBridgeReady,
  type LessonCategoryDto,
  type LessonDto,
  type LessonRecord,
} from "@/lib/bridge"

export type OpenLesson = {
  lesson: LessonDto
  category: string
  /** True while the simulator's log is being watched. */
  sync: boolean
  detail: string
}

/**
 * The lesson list, the lesson on screen, and which of its steps are done.
 *
 * Steps complete from two directions and both land here: the operator ticking
 * one off, and the machine reporting a press through the `lesson_step` event.
 * Python owns the record either way — this only mirrors it, so a step that has
 * been recorded shows immediately rather than after a round trip.
 */
export function useLessons(userId: string) {
  const [categories, setCategories] = useState<LessonCategoryDto[]>([])
  const [progress, setProgress] = useState<Record<string, LessonRecord>>({})
  const [open, setOpen] = useState<OpenLesson | null>(null)
  const [done, setDone] = useState<number[]>([])
  const [loading, setLoading] = useState(true)

  const refresh = useCallback(async () => {
    if (!userId) return
    const catalog = await fetchLessons(userId)
    setCategories(catalog.categories ?? [])
    setProgress(catalog.progress ?? {})
    setLoading(false)
  }, [userId])

  useEffect(() => {
    // The bridge is injected after mount; asking before it arrives returns an
    // empty catalog and the screen reads as "no lessons".
    void whenBridgeReady().then(refresh)
  }, [refresh])

  // The machine's own report, pushed from the tailer thread.
  useEffect(() => {
    return onEvent("lesson_step", (d) => {
      const step = d as { lesson_id: string; step_index: number }
      setDone((prev) =>
        prev.includes(step.step_index)
          ? prev
          : [...prev, step.step_index].sort((a, b) => a - b),
      )
      setProgress((prev) => {
        const record = prev[step.lesson_id] ?? { steps_done: [], last_opened: null }
        if (record.steps_done.includes(step.step_index)) return prev
        return {
          ...prev,
          [step.lesson_id]: {
            ...record,
            steps_done: [...record.steps_done, step.step_index].sort((a, b) => a - b),
          },
        }
      })
    })
  }, [])

  const select = useCallback(
    async (lessonId: string) => {
      const result = await openLesson(userId, lessonId)
      if (!result.ok || !result.lesson) return
      setDone(result.steps_done ?? [])
      setOpen({
        lesson: result.lesson,
        category: result.category ?? "",
        sync: Boolean(result.sync),
        detail: result.detail ?? "",
      })
    },
    [userId],
  )

  /** Back to the list. Stop watching the log: nothing on screen would show
   * a step completing, and the operator has moved on. */
  const close = useCallback(async () => {
    setOpen(null)
    await closeLesson()
    await refresh()
  }, [refresh])

  const tick = useCallback(
    async (stepIndex: number) => {
      if (!open) return
      setDone((prev) =>
        prev.includes(stepIndex) ? prev : [...prev, stepIndex].sort((a, b) => a - b),
      )
      await completeStep(userId, open.lesson.id, stepIndex)
    },
    [open, userId],
  )

  const restart = useCallback(async () => {
    if (!open) return
    setDone([])
    await resetLesson(userId, open.lesson.id)
    // Reopening rewires the watcher, so ordered steps wait on each other from
    // the top again exactly as they did the first time.
    await select(open.lesson.id)
  }, [open, select, userId])

  return { categories, progress, open, done, loading, select, close, tick, restart }
}
