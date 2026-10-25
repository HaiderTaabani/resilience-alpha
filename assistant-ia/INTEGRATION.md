# Intégrer l'assistant IA au dashboard (pour Ismael)

L'assistant tourne sur le PC IA : `http://192.168.137.149:8100` (réseau du groupe).
On passe par le Nginx du frontend pour que le navigateur n'ait qu'une seule origine (pas de CORS).

## 1. `services/frontend/nginx.conf` : ajouter ce bloc

```nginx
    location /api/assistant/ {
        proxy_pass http://192.168.137.149:8100/;
        proxy_read_timeout 90s;   # la 1ere reponse peut prendre 20 a 30 s (chargement du modele)
    }
```

Si l'adresse du PC IA change, c'est la seule ligne à mettre à jour.

## 2. `services/frontend/src/App.jsx` : ajouter ce composant (avant `export default function App`)

```jsx
function AssistantCard() {
  const [question, setQuestion] = useState('');
  const [answer, setAnswer] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  async function ask() {
    const q = question.trim();
    if (q.length < 3 || loading) return;
    setLoading(true);
    setError(null);
    setAnswer(null);
    try {
      const res = await fetch('/api/assistant/ask', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: q }),
        signal: AbortSignal.timeout(90000),
      });
      const json = await res.json();
      if (!res.ok) throw new Error(json.detail || 'erreur ' + res.status);
      setAnswer(json);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <Card title="Assistant operateur (IA locale)">
      <textarea
        value={question}
        onChange={(e) => setQuestion(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            ask();
          }
        }}
        maxLength={500}
        rows={2}
        placeholder="Ex. : Que fait la remediation en cas de rafale d'echecs de connexion ?"
        style={{ width: '100%', boxSizing: 'border-box', background: '#0d1117', color: '#c9d1d9', border: '1px solid #30363d', borderRadius: 6, padding: 8, fontFamily: 'inherit' }}
      />
      <button
        onClick={ask}
        disabled={loading}
        style={{ marginTop: 8, padding: '8px 14px', background: '#238636', border: 'none', borderRadius: 6, color: 'white', fontWeight: 600, cursor: 'pointer' }}
      >
        {loading ? 'Recherche...' : 'Demander'}
      </button>
      {error && <p style={{ color: '#e4514a', fontSize: 13 }}>Impossible de repondre : {error}</p>}
      {answer && (
        <div style={{ marginTop: 12, fontSize: 14, whiteSpace: 'pre-wrap' }}>
          {answer.answer}
          <div style={{ color: '#8b949e', fontSize: 12, marginTop: 8 }}>
            Sources : {answer.sources.join(', ')} - {answer.seconds} s
          </div>
        </div>
      )}
    </Card>
  );
}
```

Puis, dans `App()`, juste avant la dernière `</div>` du composant (après le bloc des 3 cartes du bas) :

```jsx
      <div style={{ marginTop: 16 }}>
        <AssistantCard />
      </div>
```

(React échappe le texte : la réponse du modèle ne peut pas injecter de HTML.)

## 3. Reconstruire le frontend

```powershell
docker compose up --build -d frontend
```

## 4. Vérifier

- Depuis le PC Hôte : `curl.exe http://192.168.137.149:8100/health` doit répondre `{"status":"ok",...}`.
- Ouvrir le dashboard (`http://127.0.0.1:8090`), poser une question dans la carte « Assistant opérateur ».
- Si la carte affiche une erreur : le PC IA doit être connecté au point d'accès `RESILIENCE-G15`, et l'assistant lancé avec
  `--host 192.168.137.149 --port 8100`.

## Remarque

Le conteneur `frontend` appelle une adresse du réseau local depuis Docker : ça marche avec Docker Desktop, mais si ça échoue
(timeout), tester `curl.exe http://192.168.137.149:8100/health` DEPUIS le conteneur :
`docker compose exec frontend wget -qO- http://192.168.137.149:8100/health`
