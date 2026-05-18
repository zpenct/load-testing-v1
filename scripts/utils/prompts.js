// Corpus prompt realistis untuk chatbot akademik UNHAS
// Distribusi: 40% RAG, 30% chitchat, 20% medium/ambiguous, 10% OOS

export const PROMPTS_CHITCHAT = [
  "halo",
  "halo, bisa bantu saya?",
  "selamat pagi",
  "terima kasih ya",
  "oke makasih",
  "permisi",
];

export const PROMPTS_RAG_SHORT = [
  "apa itu cuti akademik?",
  "berapa SKS minimal untuk lulus S1?",
  "kapan jadwal pendaftaran PMB UNHAS?",
  "apa syarat wisuda di UNHAS?",
  "fakultas apa saja yang ada di UNHAS?",
  "berapa jumlah prodi di Fakultas Teknik?",
  "apa itu KRS?",
  "jadwal kuliah Teknik Informatika semester ini ada di mana?",
];

export const PROMPTS_RAG_MEDIUM = [
  "saya mahasiswa teknik informatika semester 5, mau tanya prosedur pengambilan cuti akademik dan persyaratannya apa saja?",
  "bagaimana cara mengajukan keberatan nilai di UNHAS? apakah ada batas waktu tertentu?",
  "saya bingung perbedaan kurikulum 2020 dan 2022 di prodi informatika, bisa dijelaskan perbedaannya?",
  "apa saja mata kuliah wajib di prodi Sistem Informasi dan berapa total SKS minimalnya untuk lulus?",
  "bagaimana prosedur pindah jurusan di UNHAS? apa saja syarat akademik yang harus dipenuhi?",
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

// Weighted random picker
export function getRandomPrompt() {
  const rand = Math.random();
  if (rand < 0.30) {
    // 30% chitchat
    return PROMPTS_CHITCHAT[Math.floor(Math.random() * PROMPTS_CHITCHAT.length)];
  } else if (rand < 0.70) {
    // 40% RAG (short + medium)
    const pool = [...PROMPTS_RAG_SHORT, ...PROMPTS_RAG_MEDIUM];
    return pool[Math.floor(Math.random() * pool.length)];
  } else if (rand < 0.90) {
    // 20% ambiguous
    return PROMPTS_AMBIGUOUS[Math.floor(Math.random() * PROMPTS_AMBIGUOUS.length)];
  } else {
    // 10% out of scope
    return PROMPTS_OUT_OF_SCOPE[Math.floor(Math.random() * PROMPTS_OUT_OF_SCOPE.length)];
  }
}

export function getRAGOnlyPrompt() {
  const pool = [...PROMPTS_RAG_SHORT, ...PROMPTS_RAG_MEDIUM];
  return pool[Math.floor(Math.random() * pool.length)];
}