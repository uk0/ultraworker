pub struct Tokenizer;

impl Tokenizer {
    pub fn new() -> Self {
        Self
    }

    pub fn tokenize(&self, text: &str) -> Vec<String> {
        let mut tokens = Vec::new();
        let mut current = String::new();

        for ch in text.chars() {
            if ch.is_alphanumeric() {
                for lowered in ch.to_lowercase() {
                    current.push(lowered);
                }
            } else if !current.is_empty() {
                tokens.push(std::mem::take(&mut current));
            }
        }

        if !current.is_empty() {
            tokens.push(current);
        }

        tokens
    }
}

impl Default for Tokenizer {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::Tokenizer;

    #[test]
    fn tokenizes_korean_text() {
        let tokenizer = Tokenizer::new();
        let tokens = tokenizer.tokenize("안녕하세요 world-123 검색 테스트");
        assert!(tokens.contains(&"안녕하세요".to_string()));
        assert!(tokens.contains(&"world".to_string()));
        assert!(tokens.contains(&"123".to_string()));
        assert!(tokens.contains(&"검색".to_string()));
        assert!(tokens.contains(&"테스트".to_string()));
    }
}
