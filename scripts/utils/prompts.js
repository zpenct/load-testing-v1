// utils/prompts.js

import { randomIntBetween } from 'https://jslib.k6.io/k6-utils/1.4.0/index.js';

// ── Context injectors ──────────────────────────────────────────
const SEMESTER = ["semester 1", "semester 2", "semester 3", "semester 4",
                  "semester 5", "semester 6", "semester 7", "semester 8"];

const PRODI = [
  "Teknik Informatika", "Sistem Informasi", "Teknik Sipil",
  "Teknik Mesin", "Teknik Elektro", "Akuntansi", "Manajemen",
  "Ilmu Hukum", "Kedokteran", "Farmasi", "Psikologi", "Sastra Indonesia",
];

const OPENER = [
  "hei kak,", "permisi,", "mau tanya nih,", "boleh nanya?",
  "selamat pagi,", "selamat siang,", "maaf ganggu,", "halo,",
  "mau tanya dong,", "bisa bantu saya?",
];

function ctx() {
  const smt  = SEMESTER[randomIntBetween(0, SEMESTER.length - 1)];
  const prod = PRODI[randomIntBetween(0, PRODI.length - 1)];
  const open = OPENER[randomIntBetween(0, OPENER.length - 1)];
  return { smt, prod, open };
}

function injectShort(base) {
  const { smt, prod, open } = ctx();
  return `${open} ${base} saya mahasiswa ${prod} ${smt}`;
}

function injectMedium(base) {
  const { smt, prod, open } = ctx();
  return `${open} saya mahasiswa ${prod} ${smt}, ${base}`;
}

// ── Corpus ─────────────────────────────────────────────────────
const PROMPTS_RAG_SHORT_BASE = [
  "apa itu cuti akademik?",
  "berapa SKS minimal untuk lulus S1?",
  "kapan jadwal pendaftaran PMB UNHAS?",
  "apa syarat wisuda di UNHAS?",
  "fakultas apa saja yang ada di UNHAS?",
  "berapa jumlah prodi di Fakultas Teknik?",
  "apa itu KRS?",
  "jadwal kuliah semester ini ada di mana?",
  "bagaimana cara mengisi KRS online?",
  "apa itu IPS dan IPK?",
  "berapa batas maksimal SKS per semester?",
  "apa itu mahasiswa aktif?",
];

const PROMPTS_RAG_MEDIUM_BASE = [
  "mau tanya prosedur pengambilan cuti akademik dan persyaratannya apa saja?",
  "bagaimana cara mengajukan keberatan nilai? apakah ada batas waktu tertentu?",
  "bisa dijelaskan perbedaan kurikulum 2020 dan 2022?",
  "apa saja mata kuliah wajib dan berapa total SKS minimal untuk lulus?",
  "bagaimana prosedur pindah jurusan? apa saja syarat akademik yang harus dipenuhi?",
  "apa saja dokumen yang dibutuhkan untuk daftar ulang mahasiswa baru?",
  "bagaimana cara mengurus surat keterangan aktif kuliah?",
  "apa bedanya skripsi dan tugas akhir di UNHAS?",
];

export const PROMPTS_CHITCHAT = [
  "halo", "halo, bisa bantu saya?", "selamat pagi",
  "terima kasih ya", "oke makasih", "permisi",
];

export const PROMPTS_AMBIGUOUS = [
  "nilai saya jelek semester ini, gimana?",
  "mau tanya soal akademik",
  "ada yang bisa bantu?",
  "saya bingung masalah kuliah",
];

export const PROMPTS_OUT_OF_SCOPE = [
  "siapa presiden Indonesia sekarang?",
  "rekomendasi laptop untuk mahasiswa dong",
  "cara buat nasi goreng enak",
  "prediksi bola malam ini",
];

// ── Picker ─────────────────────────────────────────────────────
export function getRandomPrompt() {
  const rand = Math.random();
  if (rand < 0.30) {
    return PROMPTS_CHITCHAT[randomIntBetween(0, PROMPTS_CHITCHAT.length - 1)];
  } else if (rand < 0.55) {
    // RAG short — inject context
    const base = PROMPTS_RAG_SHORT_BASE[randomIntBetween(0, PROMPTS_RAG_SHORT_BASE.length - 1)];
    return injectShort(base);
  } else if (rand < 0.70) {
    // RAG medium — inject context
    const base = PROMPTS_RAG_MEDIUM_BASE[randomIntBetween(0, PROMPTS_RAG_MEDIUM_BASE.length - 1)];
    return injectMedium(base);
  } else if (rand < 0.90) {
    return PROMPTS_AMBIGUOUS[randomIntBetween(0, PROMPTS_AMBIGUOUS.length - 1)];
  } else {
    return PROMPTS_OUT_OF_SCOPE[randomIntBetween(0, PROMPTS_OUT_OF_SCOPE.length - 1)];
  }
}

export function getRAGOnlyPrompt() {
  const pool_short  = PROMPTS_RAG_SHORT_BASE;
  const pool_medium = PROMPTS_RAG_MEDIUM_BASE;
  const useShort = Math.random() < 0.6;
  if (useShort) {
    const base = pool_short[randomIntBetween(0, pool_short.length - 1)];
    return injectShort(base);
  } else {
    const base = pool_medium[randomIntBetween(0, pool_medium.length - 1)];
    return injectMedium(base);
  }
}