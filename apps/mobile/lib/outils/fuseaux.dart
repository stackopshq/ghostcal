/// IANA time zones offered by the profile picker: the ones people actually live in,
/// grouped by region. The server accepts any IANA name, so a zone missing here can
/// still be typed in the search field.
const fuseauxCourants = <String>[
  'Europe/Zurich', 'Europe/Paris', 'Europe/Brussels', 'Europe/Luxembourg',
  'Europe/Berlin', 'Europe/Vienna', 'Europe/Rome', 'Europe/Madrid', 'Europe/Lisbon',
  'Europe/London', 'Europe/Dublin', 'Europe/Amsterdam', 'Europe/Copenhagen',
  'Europe/Stockholm', 'Europe/Oslo', 'Europe/Helsinki', 'Europe/Warsaw',
  'Europe/Prague', 'Europe/Budapest', 'Europe/Athens', 'Europe/Bucharest',
  'Europe/Istanbul', 'Europe/Kyiv', 'Europe/Moscow',
  'Africa/Casablanca', 'Africa/Algiers', 'Africa/Tunis', 'Africa/Dakar',
  'Africa/Abidjan', 'Africa/Lagos', 'Africa/Cairo', 'Africa/Nairobi',
  'Africa/Johannesburg', 'Indian/Reunion', 'Indian/Mauritius',
  'America/Montreal', 'America/Toronto', 'America/New_York', 'America/Chicago',
  'America/Denver', 'America/Los_Angeles', 'America/Vancouver', 'America/Mexico_City',
  'America/Bogota', 'America/Lima', 'America/Santiago', 'America/Sao_Paulo',
  'America/Argentina/Buenos_Aires', 'America/Martinique', 'America/Guadeloupe',
  'America/Cayenne', 'Pacific/Honolulu', 'Pacific/Tahiti', 'Pacific/Noumea',
  'Asia/Dubai', 'Asia/Jerusalem', 'Asia/Beirut', 'Asia/Riyadh', 'Asia/Karachi',
  'Asia/Kolkata', 'Asia/Dhaka', 'Asia/Bangkok', 'Asia/Ho_Chi_Minh', 'Asia/Singapore',
  'Asia/Hong_Kong', 'Asia/Shanghai', 'Asia/Taipei', 'Asia/Seoul', 'Asia/Tokyo',
  'Australia/Perth', 'Australia/Sydney', 'Australia/Melbourne', 'Pacific/Auckland',
  'UTC',
];

/// The zones matching [requete], case- and separator-insensitive ("new york",
/// "new_york" and "York" all find America/New_York).
List<String> filtrerLesFuseaux(String requete) {
  final cle = requete.toLowerCase().replaceAll(RegExp(r'[\s_/]+'), ' ').trim();
  if (cle.isEmpty) return fuseauxCourants;
  return fuseauxCourants
      .where((f) => f.toLowerCase().replaceAll(RegExp(r'[_/]+'), ' ').contains(cle))
      .toList();
}
