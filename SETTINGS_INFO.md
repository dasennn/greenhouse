# User Settings και Production Installation

## Αποθήκευση Ρυθμίσεων Χρήστη

Η εφαρμογή χρησιμοποιεί το `QSettings` της Qt για να αποθηκεύει τις προτιμήσεις του χρήστη. Οι ρυθμίσεις διατηρούνται μεταξύ των εκτελέσεων της εφαρμογής.

### Τοποθεσία Αποθήκευσης

Οι ρυθμίσεις αποθηκεύονται αυτόματα στις εξής τοποθεσίες ανάλογα με το λειτουργικό σύστημα:

- **macOS**: `~/Library/Preferences/com.Greenhouse.GreenhouseApp.plist`
- **Windows**: `HKEY_CURRENT_USER\Software\Greenhouse\GreenhouseApp` (Registry)
- **Linux**: `~/.config/Greenhouse/GreenhouseApp.conf`

### Διαθέσιμες Ρυθμίσεις

#### 1. **Μέγιστο Όριο Zoom Out** (`view/max_grid_meters`)
- Προεπιλογή: `500` μέτρα
- Εύρος: `10` - `10000` μέτρα
- Πρόσβαση: Μενού → Ρυθμίσεις → Μέγιστο Όριο Zoom Out…
- Περιγραφή: Ορίζει πόσο μακριά μπορεί να κάνει zoom out ο χρήστης

#### 2. **Αυτόματη Αποθήκευση** (`general/autosave_enabled`)
- Προεπιλογή: `True` (ενεργοποιημένο)
- Πρόσβαση: Μενού → Ρυθμίσεις → Αυτόματη Αποθήκευση (checkbox)
- Περιγραφή: Ενεργοποιεί/απενεργοποιεί την αυτόματη αποθήκευση

#### 3. **Διάστημα Αυτόματης Αποθήκευσης** (`general/autosave_interval`)
- Προεπιλογή: `30000` ms (30 δευτερόλεπτα)
- Περιγραφή: Πόσο συχνά γίνεται η αυτόματη αποθήκευση

#### 4. **Τελευταίος Φάκελος** (`paths/last_directory`)
- Προεπιλογή: (κενό)
- Περιγραφή: Θυμάται τον τελευταίο φάκελο που άνοιξε/αποθήκευσε ο χρήστης

### Μελλοντικές Ρυθμίσεις (Προτάσεις)

Στο μέλλον μπορούν να προστεθούν:

```python
# Window state
"window/geometry"           # Μέγεθος και θέση παραθύρου
"window/state"             # Κατάσταση docks/toolbars
"window/maximized"         # Μεγιστοποιημένο παράθυρο

# UI Preferences
"ui/theme"                 # Θέμα εμφάνισης (light/dark)
"ui/language"              # Γλώσσα εφαρμογής

# Defaults
"defaults/grid_preset"     # Προεπιλεγμένο grid (5x3, κλπ)
"defaults/material_catalog" # Προεπιλεγμένος κατάλογος υλικών

# Export
"export/last_format"       # Τελευταία μορφή εξαγωγής (CSV, PDF, κλπ)
"export/include_prices"    # Συμπερίληψη τιμών στην εξαγωγή
```

## Production Installation - Καθαρισμός Ρυθμίσεων

### Για καθαρό installation (πρώτη εγκατάσταση)

Οι ρυθμίσεις δημιουργούνται **αυτόματα** όταν:
1. Ο χρήστης εκτελέσει την εφαρμογή για πρώτη φορά
2. Αλλάξει μια ρύθμιση μέσω του UI

**Δεν χρειάζεται** να κάνεις τίποτα στο installer - οι προεπιλεγμένες τιμές είναι ενσωματωμένες στον κώδικα.

### Για reset/επαναφορά ρυθμίσεων

Αν χρειαστεί να επαναφέρεις τις ρυθμίσεις στις προεπιλογές:

#### macOS
```bash
defaults delete com.Greenhouse.GreenhouseApp
# ή διέγραψε το αρχείο:
rm ~/Library/Preferences/com.Greenhouse.GreenhouseApp.plist
```

#### Windows
```batch
reg delete "HKEY_CURRENT_USER\Software\Greenhouse\GreenhouseApp" /f
```

#### Linux
```bash
rm ~/.config/Greenhouse/GreenhouseApp.conf
```

### Για τον Installer

Κατά την εγκατάσταση:
- **ΜΗΝ** προ-δημιουργήσεις αρχεία ρυθμίσεων
- **ΜΗΝ** διαγράψεις υπάρχουσες ρυθμίσεις (αν ο χρήστης κάνει update)
- Οι ρυθμίσεις θα δημιουργηθούν αυτόματα με τις σωστές προεπιλογές

Κατά την απεγκατάσταση:
- **ΠΡΟΣΟΧΗ**: Ρώτησε τον χρήστη αν θέλει να κρατήσει τις ρυθμίσεις του
- Προαιρετικά, μπορείς να προσφέρεις επιλογή για διαγραφή των ρυθμίσεων

## Χρήση στον Κώδικα

### Προσθήκη νέας ρύθμισης

```python
# Στο _load_user_settings()
new_setting = self.settings.value("category/setting_name", default_value, type=bool)
self.some_property = new_setting

# Στο _save_user_settings()
self.settings.setValue("category/setting_name", self.some_property)
```

### Κατηγορίες ρυθμίσεων

- `view/` - Ρυθμίσεις προβολής (zoom, grid, κλπ)
- `general/` - Γενικές ρυθμίσεις (autosave, κλπ)
- `paths/` - Μονοπάτια και φάκελοι
- `window/` - Κατάσταση παραθύρου
- `ui/` - Προτιμήσεις UI

## Debugging

Για να δεις τις τρέχουσες ρυθμίσεις:

```python
# Προσθήκη στο κώδικα (debugging)
print("All settings:", self.settings.allKeys())
for key in self.settings.allKeys():
    print(f"{key}: {self.settings.value(key)}")
```

## Security Note

Οι ρυθμίσεις αποθηκεύονται σε **plaintext** (εκτός από το Windows Registry).
**ΜΗΝ** αποθηκεύσεις ευαίσθητα δεδομένα (passwords, API keys, κλπ) στο QSettings.
Για ευαίσθητα δεδομένα, χρησιμοποίησε το keyring του συστήματος.
