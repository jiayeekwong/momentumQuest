export const PENDING_REVIEWS_CHANGED_EVENT = 'mq:pending-reviews-changed';

/** Ask persistent admin UI, such as the sidebar, to refresh its queue count. */
export function notifyPendingReviewsChanged() {
  window.dispatchEvent(new Event(PENDING_REVIEWS_CHANGED_EVENT));
}
