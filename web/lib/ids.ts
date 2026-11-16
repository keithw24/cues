/** The one definition of each identifier shape the dashboard validates. */

/** Station and seat ids: 1-64 letters, digits, "_" or "-" (matches vision/station.py). */
export const STATION_ID = /^[A-Za-z0-9_-]{1,64}$/;
export const SEAT_ID = STATION_ID;

/** A phone number in E.164 form, e.g. +12025550101 (matches agent and notification code). */
export const E164 = /^\+[1-9][0-9]{7,14}$/;
