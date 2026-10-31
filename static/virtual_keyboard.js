/**
 * Virtual Keyboard for Multilingual Support
 * Shows floating keyboard when user types in non-English languages
 */

class VirtualKeyboard {
    constructor() {
        this.isOpen = false;
        this.activeInput = null;
        this.currentLanguage = 'en';
        
        // Language-specific keyboard layouts
        this.layouts = {
            'en': this.getEnglishLayout(),
            'ta': this.getTamilLayout(),
            'hi': this.getHindiLayout(),
            'te': this.getTeluguLayout(),
            'kn': this.getKannadaLayout(),
        };
        
        this.init();
    }
    
    init() {
        // Create keyboard container
        this.createKeyboardUI();
        
        // Listen for language changes
        document.addEventListener('languageChanged', (e) => {
            this.currentLanguage = e.detail.language;
            if (this.isOpen) {
                this.updateKeyboard();
            }
        });
        
        // Add event listeners to all textarea and input fields
        document.querySelectorAll('input, textarea').forEach(el => {
            el.addEventListener('focus', (e) => {
                if (this.currentLanguage !== 'en') {
                    this.open(e.target);
                }
            });
            
            el.addEventListener('blur', () => {
                setTimeout(() => this.close(), 200);
            });
        });
    }
    
    createKeyboardUI() {
        const keyboardHTML = `
            <div id="virtualKeyboard" class="virtual-keyboard" style="display:none;">
                <div class="keyboard-header">
                    <span id="keyboardTitle">Keyboard</span>
                    <button id="closeKeyboard" class="close-btn">&times;</button>
                </div>
                <div id="keyboardContent" class="keyboard-content"></div>
            </div>
        `;
        
        document.body.insertAdjacentHTML('beforeend', keyboardHTML);
        
        // Style
        const style = document.createElement('style');
        style.textContent = `
            .virtual-keyboard {
                position: fixed;
                bottom: 0;
                left: 0;
                right: 0;
                background: #f0f0f0;
                border-top: 2px solid #0066cc;
                box-shadow: 0 -2px 10px rgba(0,0,0,0.1);
                z-index: 10000;
                max-height: 250px;
                overflow-y: auto;
                font-family: Arial, sans-serif;
            }
            
            .keyboard-header {
                display: flex;
                justify-content: space-between;
                align-items: center;
                padding: 10px 15px;
                background: #0066cc;
                color: white;
                font-weight: bold;
            }
            
            .close-btn {
                background: none;
                border: none;
                color: white;
                font-size: 24px;
                cursor: pointer;
            }
            
            .keyboard-content {
                padding: 10px;
                display: flex;
                flex-wrap: wrap;
                gap: 5px;
            }
            
            .keyboard-key {
                background: white;
                border: 1px solid #999;
                border-radius: 4px;
                padding: 8px 12px;
                cursor: pointer;
                font-size: 14px;
                text-align: center;
                user-select: none;
                transition: all 0.1s;
                flex: 1 1 auto;
                min-width: 30px;
            }
            
            .keyboard-key:hover {
                background: #e6f2ff;
                border-color: #0066cc;
            }
            
            .keyboard-key:active {
                background: #0066cc;
                color: white;
                transform: scale(0.95);
            }
            
            .keyboard-key.space {
                flex: 1 1 100%;
                min-width: 100%;
                padding: 10px;
            }
            
            .keyboard-key.backspace {
                background: #ff6b6b;
                color: white;
            }
            
            .keyboard-key.backspace:hover {
                background: #ff5252;
            }
        `;
        document.head.appendChild(style);
        
        // Event listeners
        document.getElementById('closeKeyboard').addEventListener('click', () => this.close());
    }
    
    open(inputElement) {
        this.activeInput = inputElement;
        this.isOpen = true;
        document.getElementById('virtualKeyboard').style.display = 'block';
        this.updateKeyboard();
    }
    
    close() {
        this.isOpen = false;
        document.getElementById('virtualKeyboard').style.display = 'none';
        this.activeInput = null;
    }
    
    updateKeyboard() {
        const layout = this.layouts[this.currentLanguage] || this.layouts['en'];
        const content = document.getElementById('keyboardContent');
        content.innerHTML = '';
        
        const title = document.getElementById('keyboardTitle');
        title.textContent = this.getLanguageName(this.currentLanguage);
        
        layout.forEach(key => {
            if (key === ' ') {
                const spaceBtn = document.createElement('button');
                spaceBtn.className = 'keyboard-key space';
                spaceBtn.textContent = 'Space';
                spaceBtn.addEventListener('click', () => this.typeCharacter(' '));
                content.appendChild(spaceBtn);
            } else if (key === 'BACKSPACE') {
                const backBtn = document.createElement('button');
                backBtn.className = 'keyboard-key backspace';
                backBtn.textContent = '← Backspace';
                backBtn.addEventListener('click', () => this.backspace());
                content.appendChild(backBtn);
            } else {
                const btn = document.createElement('button');
                btn.className = 'keyboard-key';
                btn.textContent = key;
                btn.addEventListener('click', () => this.typeCharacter(key));
                content.appendChild(btn);
            }
        });
    }
    
    typeCharacter(char) {
        if (!this.activeInput) return;
        
        const start = this.activeInput.selectionStart;
        const end = this.activeInput.selectionEnd;
        const text = this.activeInput.value;
        
        this.activeInput.value = text.substring(0, start) + char + text.substring(end);
        this.activeInput.selectionStart = this.activeInput.selectionEnd = start + char.length;
        
        // Trigger input event
        this.activeInput.dispatchEvent(new Event('input', { bubbles: true }));
    }
    
    backspace() {
        if (!this.activeInput) return;
        
        const start = this.activeInput.selectionStart;
        const end = this.activeInput.selectionEnd;
        const text = this.activeInput.value;
        
        if (start === end && start > 0) {
            this.activeInput.value = text.substring(0, start - 1) + text.substring(start);
            this.activeInput.selectionStart = this.activeInput.selectionEnd = start - 1;
        } else {
            this.activeInput.value = text.substring(0, start) + text.substring(end);
            this.activeInput.selectionStart = this.activeInput.selectionEnd = start;
        }
        
        this.activeInput.dispatchEvent(new Event('input', { bubbles: true }));
    }
    
    getLanguageName(code) {
        const names = {
            'en': 'English',
            'ta': 'Tamil',
            'hi': 'Hindi',
            'te': 'Telugu',
            'kn': 'Kannada',
        };
        return names[code] || 'Keyboard';
    }
    
    // Keyboard layouts for each language
    getEnglishLayout() {
        return ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h', 'i', 'j', 'k', 'l', 'm',
                'n', 'o', 'p', 'q', 'r', 's', 't', 'u', 'v', 'w', 'x', 'y', 'z',
                '0', '1', '2', '3', '4', '5', '6', '7', '8', '9',
                ' ', 'BACKSPACE'];
    }
    
    getTamilLayout() {
        return ['ஆ', 'ஈ', 'ஐ', 'ஊ', 'ஏ', 'ஒ', 'க', 'ங', 'ச', 'ஞ',
                'ட', 'ண', 'த', 'ந', 'ப', 'ம', 'ய', 'ர', 'ல', 'வ',
                'ழ', 'ள', 'ற', 'ன', ' ', 'BACKSPACE'];
    }
    
    getHindiLayout() {
        return ['अ', 'आ', 'इ', 'ई', 'उ', 'ऊ', 'ए', 'ऐ', 'ओ', 'औ',
                'क', 'ख', 'ग', 'घ', 'ङ', 'च', 'छ', 'ज', 'झ', 'ञ',
                'ट', 'ठ', 'ड', 'ढ', 'ण', ' ', 'BACKSPACE'];
    }
    
    getTeluguLayout() {
        return ['అ', 'ఆ', 'ఇ', 'ఈ', 'ఉ', 'ఊ', 'ఋ', 'ఌ', 'ఎ', 'ఏ',
                'ఐ', 'ఒ', 'ఓ', 'ఔ', 'క', 'ఖ', 'గ', 'ఘ', 'ఙ', 'చ',
                'ఛ', 'జ', 'ఝ', 'ఞ', ' ', 'BACKSPACE'];
    }
    
    getKannadaLayout() {
        return ['ಅ', 'ಆ', 'ಇ', 'ಈ', 'ಉ', 'ಊ', 'ಋ', 'ಎ', 'ಏ', 'ಐ',
                'ಒ', 'ಓ', 'ಔ', 'ಕ', 'ಖ', 'ಗ', 'ಘ', 'ಙ', 'ಚ', 'ಛ',
                'ಜ', 'ಝ', 'ಞ', ' ', 'BACKSPACE'];
    }
}

// Initialize when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
        new VirtualKeyboard();
    });
} else {
    new VirtualKeyboard();
}

// Function to change language and trigger keyboard update
function changeLanguage(languageCode) {
    const event = new CustomEvent('languageChanged', {
        detail: { language: languageCode }
    });
    document.dispatchEvent(event);
}
