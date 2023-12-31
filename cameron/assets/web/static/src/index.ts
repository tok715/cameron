enum WebSocketFrameKind {
    AudioInput = 0x01,
    AudioTranscribeResult = 0x02,
    AudioSynthesizeResult = 0x03,
    ModelGenerationResult = 0x04,
}

async function wait(ms: number) {
    return new Promise(resolve => setTimeout(resolve, ms))
}

function output(color: string, text: string) {
    const date = moment().format('hh:mm:ss.SSS')
    $("#div-output").prepend(
        `<p class="card-text mb-0"><span class="text-muted me-2">${date}</span><span class="text-${color}">${text}</span></p>`
    )
}

function info(text: string) {
    output('info', text)
}

function error(text: string) {
    output('danger', text)
}

function downloadBlob(name: string, blob: Blob) {
    const a: JQuery<HTMLLinkElement> = $("<a style='display: none;'/>");
    const url = window.URL.createObjectURL(blob);
    a.attr("href", url);
    a.attr("download", name);
    $("body").append(a);
    a[0].click();
    window.URL.revokeObjectURL(url);
    a.remove();
}

const state: {
    ws?: WebSocket;
    audioStream?: MediaStream;
    audioContext?: AudioContext;
} = {};

class AudioSynthesizeQueue {
    queue: Uint8Array[] = []

    triggered = false

    audioContextProvider: () => AudioContext | undefined

    constructor(audioContextProvider: () => AudioContext | undefined) {
        this.audioContextProvider = audioContextProvider
    }

    async trigger() {
        if (this.triggered) {
            return
        }
        this.triggered = true
        try {
            while (true) {
                const data = this.queue.shift()
                if (!data) {
                    break
                }
                const ctx = this.audioContextProvider()
                if (!ctx) {
                    this.queue = [];
                    return
                }
                const buf = await ctx.decodeAudioData(data.buffer.slice(data.byteOffset, data.byteLength))

                const src = ctx.createBufferSource()
                src.buffer = buf
                src.connect(ctx.destination)
                src.start()

                await wait(buf.duration * 1000)
            }
        } catch (e) {
            error(`audio queue error: ${e}`)
            this.queue = []
        } finally {
            this.triggered = false
        }
    }

    async add(data: Uint8Array) {
        this.queue.push(data)
        this.trigger().then(() => {
        })
    }

}

const audioQueue = new AudioSynthesizeQueue(() => state.audioContext)


async function setupWebSocket() {
    const ws = new WebSocket(`ws://${location.host}/ws`)
    ws.binaryType = 'arraybuffer'

    ws.onopen = function () {
        info('websocket connection opened')
        state.ws = ws;
    }

    ws.onerror = function (e) {
        error(`websocket connection error: ${e}`)
    }

    ws.onclose = function () {
        error('websocket connection closed, reconnecting...')

        state.ws = undefined

        setTimeout(function () {
            setupWebSocket()
        }, 3000)
    }

    ws.onmessage = async function (e) {
        const data = new Uint8Array(e.data);
        switch (data[0]) {
            case WebSocketFrameKind.AudioTranscribeResult:
                await handleAudioTranscribe(data.subarray(1))
                break
            case WebSocketFrameKind.AudioSynthesizeResult:
                await audioQueue.add(data.subarray(1))
                break
            case WebSocketFrameKind.ModelGenerationResult:
                const result = new TextDecoder().decode(data.subarray(1))
                info(`model generation result: ${result}`)
                break
        }
    }
}

async function handleAudioTranscribe(data: Uint8Array) {
    const result = new TextDecoder().decode(data)
    info(`transcribe result: ${result}`)
}


async function setupAudioStream() {
    if (!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia)) {
        throw new Error('audio recording not supported')
    }
    info('audio recording is supported')
    const stream = await navigator.mediaDevices.getUserMedia({audio: true});
    info('microphone stream started')

    state.audioStream = stream;
}

async function setupAudioProcessor() {
    if (!state.audioStream) {
        throw new Error('audio stream not initialized')
    }
    const trackProcessor = new MediaStreamTrackProcessor(
        {
            track: state.audioStream.getAudioTracks()[0]
        }
    )
    trackProcessor.readable.pipeTo(new WritableStream({
        write: function (frame) {
            if (!state.ws) {
                return;
            }
            if (state.ws.readyState !== WebSocket.OPEN) {
                return
            }

            const data = audiodata2pcm(frame)

            if (!data) {
                return;
            }

            // TODO: force convert endianness
            const ws_data = new Int8Array(data.length * 2 + 1)
            ws_data[0] = WebSocketFrameKind.AudioInput;
            ws_data.set(new Int8Array(data.buffer), 1)
            state.ws.send(ws_data)
        },
        close() {
            info(`track processor closed`)
        }
    })).then(function () {
        error('track processor pipeTo failed')
    });
}

async function setupAudioContext() {
    state.audioContext = new AudioContext()
    info('audio context created')
}

async function setupSynthesizeButton() {
    $('#btn-start').click(async function () {
        $('#btn-start').attr('disabled', 'disabled')

        await setupAudioContext()
        await setupWebSocket();
        await setupAudioStream();
        await setupAudioProcessor();
    })
}

$(async function () {
    await setupSynthesizeButton();
})